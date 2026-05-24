"""Audit export endpoint — GET /v1/audit/{trace_id}.

Returns complete evidence for a given trace_id, signed with HMAC-SHA256
using settings.api_secret_key.  This endpoint is strictly read-only.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from core.auth_oidc import require_auth
from core.logging import get_logger
from core.tsa import request_tsa_token
from core.vault_transit import sign_data
from db.models.finding import Finding
from db.models.operation import Operation
from db.session import get_db
from schemas.audit import (
    ArtifactAuditSchema,
    AuditExportResponse,
    FindingAuditSchema,
    RedactionAuditSchema,
)
from schemas.sarif import audit_to_sarif

router = APIRouter()
logger = get_logger(__name__)


def compute_hmac(payload: dict, secret: str) -> str:
    """Compute HMAC-SHA256 of JSON-serialized payload (keys sorted, default=str)."""
    data = json.dumps(payload, sort_keys=True, default=str).encode()
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


async def get_audit_export(
    trace_id: UUID,
    db: AsyncSession,
    actor_id: str = "anonymous",
    http_client: httpx.AsyncClient | None = None,
) -> AuditExportResponse | None:
    """Core audit logic — reusable by HTTP endpoint and MCP tool.

    Returns None when the trace_id is not found (caller decides how to surface).
    """
    # Load operation with all related data in a single round-trip
    stmt = (
        select(Operation)
        .where(Operation.trace_id == trace_id)
        .options(
            selectinload(Operation.findings).selectinload(Finding.redactions),
            selectinload(Operation.redactions),
            selectinload(Operation.artifacts),
        )
    )
    result = await db.execute(stmt)
    operation: Operation | None = result.scalars().first()

    if operation is None:
        logger.warning(
            "audit.export.not_found",
            trace_id=str(trace_id),
            requested_by=actor_id,
        )
        return None

    exported_at = datetime.now(UTC)

    # Serialize Operation fields
    operation_dict: dict = {
        "id": str(operation.id),
        "trace_id": str(operation.trace_id),
        "actor_id": str(operation.actor_id),
        "actor_type": operation.actor_type,
        "document_id": str(operation.document_id),
        "artifact_digest": operation.artifact_digest,
        "policy_version": operation.policy_version,
        "status": operation.status,
        "created_at": operation.created_at.isoformat() if operation.created_at else None,
        "completed_at": operation.completed_at.isoformat() if operation.completed_at else None,
    }

    findings = [
        FindingAuditSchema(
            id=f.id,
            detector=f.detector,
            rule_id=f.rule_id,
            span_start=f.span_start,
            span_end=f.span_end,
            confidence=f.confidence,
            severity=f.severity,
            explanation=f.explanation,
        )
        for f in operation.findings
    ]

    redactions = [
        RedactionAuditSchema(
            id=r.id,
            finding_id=r.finding_id,
            redaction_type=r.redaction_type,
            policy_version=r.policy_version,
            applied_at=r.applied_at,
            approved_by=r.approved_by,
            approval_trace_id=r.approval_trace_id,
        )
        for r in operation.redactions
    ]

    artifacts = [
        ArtifactAuditSchema(
            id=a.id,
            artifact_type=a.artifact_type,
            minio_key=a.minio_key,
            digest=a.digest,
            worm_locked=a.worm_locked,
            created_at=a.created_at,
        )
        for a in operation.artifacts
    ]

    # Build the signable payload (everything except the signature itself)
    signable: dict = {
        "trace_id": str(trace_id),
        "exported_at": exported_at.isoformat(),
        "operation": operation_dict,
        "findings": [f.model_dump(mode="json") for f in findings],
        "redactions": [r.model_dump(mode="json") for r in redactions],
        "artifacts": [a.model_dump(mode="json") for a in artifacts],
    }

    signature = compute_hmac(signable, settings.api_secret_key)

    # F6-B1: Request TSA timestamp for non-repudiation
    tsa_token_b64: str | None = None
    if settings.tsa_enabled:
        signable_bytes = json.dumps(signable, sort_keys=True, default=str).encode()
        tsa_result = await request_tsa_token(signable_bytes, http_client=http_client)
        if tsa_result:
            tsa_token_b64 = tsa_result.token_b64

    # F6-B2: Chain hash — read from operation if available
    _raw_chain = getattr(operation, "chain_hash", None)
    chain_hash_val: str | None = _raw_chain if isinstance(_raw_chain, str) else None

    # F6-B3: Digital signature via OpenBao Transit
    digital_sig: str | None = None
    try:
        sig_data = json.dumps(signable, sort_keys=True, default=str).encode()
        digital_sig = await sign_data(sig_data, http_client=http_client)
    except Exception as exc:
        logger.warning("audit.vault_sign_failed", error=str(exc))

    logger.info(
        "audit.export",
        trace_id=str(trace_id),
        requested_by=actor_id,
        findings_count=len(findings),
        redactions_count=len(redactions),
        artifacts_count=len(artifacts),
        has_tsa=tsa_token_b64 is not None,
        has_chain_hash=chain_hash_val is not None,
        has_digital_sig=digital_sig is not None,
    )

    return AuditExportResponse(
        trace_id=trace_id,
        exported_at=exported_at,
        operation=operation_dict,
        findings=findings,
        redactions=redactions,
        artifacts=artifacts,
        hmac_signature=signature,
        sanitized_document=operation.sanitized_text,
        tsa_token=tsa_token_b64,
        chain_hash=chain_hash_val,
        digital_signature=digital_sig,
    )


class VerificationKeyResponse(BaseModel):
    algorithm: str
    key_hint: str
    instructions: str
    # F6-B3: Transit public key for digital signature verification
    transit_public_key: str | None = None
    transit_algorithm: str | None = None


@router.get("/audit/verification-key", response_model=VerificationKeyResponse, tags=["audit"])
async def verification_key(request: Request) -> VerificationKeyResponse:
    """
    Return the public HMAC verification hint and Transit public key.

    No authentication required — this is informational metadata only.
    The HMAC secret key itself is never exposed; only the first 8 characters
    are returned as an identifier hint. The Transit public key is fully
    exportable for offline signature verification.
    """
    key_hint = settings.api_secret_key[:8] + "..."
    instructions = (
        "Para verificar la integridad de un export de auditoría:\n"
        "\n"
        "1. HMAC: verificar hmac_signature con la clave secreta compartida.\n"
        "2. Digital signature: verificar digital_signature con la clave pública Transit.\n"
        "3. TSA: verificar tsa_token con openssl ts -verify.\n"
        "4. Chain hash: GET /v1/audit/chain/verify para validar cadena completa.\n"
    )

    # Try to fetch Transit public key
    transit_pub_key: str | None = None
    transit_algo: str | None = None
    try:
        from core.vault_transit import get_public_key
        http_client = getattr(request.app.state, "http_client", None)
        key_info = await get_public_key(http_client=http_client)
        if key_info:
            transit_pub_key = key_info.get("public_key_pem")
            transit_algo = key_info.get("algorithm")
    except Exception:
        pass  # Vault unavailable — return without Transit key

    logger.info("audit.verification_key.requested")
    return VerificationKeyResponse(
        algorithm="HMAC-SHA256",
        key_hint=key_hint,
        instructions=instructions,
        transit_public_key=transit_pub_key,
        transit_algorithm=transit_algo,
    )


@router.get("/audit/{trace_id}", tags=["audit"])
async def audit_export_endpoint(
    request: Request,
    trace_id: UUID,
    actor: Annotated[dict, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: Annotated[str, Query(description="Response format: 'json' (default) or 'sarif'")] = "json",
) -> AuditExportResponse | dict:
    """
    Return full audit evidence for the operation identified by trace_id.

    Requires a valid Bearer token (any authenticated user).
    The response payload is signed with HMAC-SHA256 so consumers can verify
    integrity without trusting the transport layer.

    Use ``?format=sarif`` to receive the findings in SARIF 2.1.0 format,
    compatible with GitHub Advanced Security, VS Code, and other SARIF tools.
    """
    actor_id: str = str(actor.get("sub", "unknown"))
    http_client: httpx.AsyncClient | None = getattr(request.app.state, "http_client", None)
    result = await get_audit_export(trace_id, db, actor_id=actor_id, http_client=http_client)
    if result is None:
        raise HTTPException(status_code=404, detail="trace_id not found")

    # Access control: owner, reviewer, or admin can view audit exports
    roles = actor.get("realm_access", {}).get("roles", [])
    is_privileged = "reviewer" in roles or "admin" in roles
    is_owner = result.operation.get("actor_id") == actor_id
    if not is_owner and not is_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: only the operation owner, reviewers, or admins can view audit exports",
        )

    if format == "sarif":
        sarif_output = audit_to_sarif(result)
        return sarif_output.model_dump(by_alias=True)

    return result


# ── F6-B2: Chain verification endpoint ──────────────────────────────────────


class ChainVerifyResponse(BaseModel):
    valid: bool
    checked: int
    first_broken_at: str | None
    gaps: list[str]


@router.get("/audit/chain/verify", response_model=ChainVerifyResponse, tags=["audit"])
async def verify_chain_endpoint(
    actor: Annotated[dict, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChainVerifyResponse:
    """Verify the integrity of the operation hash chain for the caller's tenant.

    Walks the chain from the first operation and verifies each chain_hash
    matches SHA256(prev_chain_hash + operation_hash). Any tampering or
    deletion of intermediate records will break the chain.

    Requires admin or reviewer role.
    """
    from core.auth_oidc import get_roles
    from core.chain import verify_chain
    from core.constants import DEFAULT_TENANT_ID

    roles = get_roles(actor)
    if "admin" not in roles and "reviewer" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin or reviewer role required to verify chain",
        )

    # Resolve tenant from JWT
    tenant_id_str = actor.get("tenant_id", "")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID

    result = await verify_chain(db, tenant_id)
    return ChainVerifyResponse(**result)
