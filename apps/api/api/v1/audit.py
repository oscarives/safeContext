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
from sqlalchemy import func, select
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

    # F7-5: prefer the WRITE-TIME signature persisted on the operation. This is
    # the authoritative non-repudiation evidence — it signs the canonical
    # operation_hash at the moment the event completed, not a later view of the
    # DB built at export time. Only fall back to a read-time signature for legacy
    # operations sealed before F7-5 (event_signature is NULL).
    _raw_event_sig = getattr(operation, "event_signature", None)
    event_signature: str | None = _raw_event_sig if isinstance(_raw_event_sig, str) else None
    _raw_signed_at = getattr(operation, "event_signed_at", None)
    event_signed_at = _raw_signed_at if isinstance(_raw_signed_at, datetime) else None
    _raw_key_version = getattr(operation, "signing_key_version", None)
    signing_key_version: int | None = _raw_key_version if isinstance(_raw_key_version, int) else None

    digital_sig: str | None = None
    signature_at_write_time = False
    if event_signature is not None:
        digital_sig = event_signature
        signature_at_write_time = True
    else:
        # Legacy fallback: sign the exported view at read-time.
        try:
            sig_data = json.dumps(signable, sort_keys=True, default=str).encode()
            digital_sig = await sign_data(sig_data, http_client=http_client)
        except Exception as exc:
            logger.warning("audit.vault_sign_failed", error=str(exc))

    # F7-4 (H2): fail-closed when the asymmetric signature is mandatory.
    # In production (audit_require_digital_signature=True) an export without a
    # real non-repudiation signature is worthless as evidence, so we refuse to
    # emit it instead of falling back to the HMAC-only checksum. Default False
    # keeps dev/tests/air-gapped (no Vault) working unchanged.
    if settings.audit_require_digital_signature and digital_sig is None:
        logger.error(
            "audit.export.signature_required_unavailable",
            trace_id=str(trace_id),
            requested_by=actor_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Digital signature is required but the signing service is "
                "unavailable; audit export withheld (fail-closed)."
            ),
        )

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
        signature_at_write_time=signature_at_write_time,
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
        signature_at_write_time=signature_at_write_time,
        event_signed_at=event_signed_at,
        signing_key_version=signing_key_version,
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
    # F7-6: signed-anchor cross-check. anchored=False when no anchor exists yet
    # (chain is only tamper-evident). When anchored, anchor_valid is the result
    # of verifying the anchor's asymmetric signature and anchor_head_matches
    # whether the live chain head still equals the signed one.
    anchored: bool = False
    anchor_valid: bool | None = None
    anchor_head_matches: bool | None = None


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

    # F7-6: cross-check the live chain head against the latest signed anchor.
    # Walking the chain alone is only tamper-EVIDENT (an insider with DB write
    # access can recompute every chain_hash). The signed anchor makes it
    # tamper-PROOF: a rewritten chain produces a head that no longer matches the
    # asymmetrically-signed anchor, and the insider cannot forge that signature.
    anchor_status = await _verify_latest_anchor(db, tenant_id)
    return ChainVerifyResponse(**result, **anchor_status)


# ── F7-6: signed chain head anchoring ────────────────────────────────────────


async def _verify_latest_anchor(db: AsyncSession, tenant_id: UUID) -> dict:
    """Verify the most recent signed anchor for a tenant against the live head.

    Returns a dict with ``anchored`` / ``anchor_valid`` / ``anchor_head_matches``
    suitable for splatting into ChainVerifyResponse.
    """
    from db.evidence import get_latest_chain_hash
    from db.models.chain_anchor import ChainAnchor

    result = await db.execute(
        select(ChainAnchor)
        .where(ChainAnchor.tenant_id == tenant_id)
        .order_by(ChainAnchor.created_at.desc())
        .limit(1)
    )
    anchor: ChainAnchor | None = result.scalars().first()
    if anchor is None:
        return {"anchored": False, "anchor_valid": None, "anchor_head_matches": None}

    # Does the anchored head still match the most recent live chain head?
    live_head = await get_latest_chain_hash(db, tenant_id)
    head_matches = live_head == anchor.chain_head_hash

    # Verify the asymmetric signature over the anchored head.
    from core.vault_transit import verify_signature

    try:
        signed_valid = await verify_signature(
            bytes.fromhex(anchor.chain_head_hash),
            anchor.signature,
            key_version=anchor.signing_key_version or 1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit.anchor.verify_error", error=str(exc))
        signed_valid = False

    return {
        "anchored": True,
        "anchor_valid": bool(signed_valid),
        "anchor_head_matches": head_matches,
    }


class ChainAnchorResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    chain_head_hash: str
    operations_count: int
    signing_key_version: int | None
    has_tsa: bool
    created_at: datetime


@router.post(
    "/audit/chain/anchor",
    response_model=ChainAnchorResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["audit"],
)
async def create_chain_anchor(
    request: Request,
    actor: Annotated[dict, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChainAnchorResponse:
    """Create a signed checkpoint (anchor) of the current chain head (F7-6).

    Signs the latest per-tenant chain head with the asymmetric Vault Transit key
    (and, when enabled, an RFC 3161 TSA token) and persists it in
    ``chain_anchors``. Subsequent chain verifications cross-check the live head
    against this signed anchor, turning the chain tamper-proof.

    Requires admin role.
    """
    from core.auth_oidc import get_roles
    from core.constants import DEFAULT_TENANT_ID
    from db.evidence import GENESIS_HASH, get_latest_chain_hash, sign_operation_hash
    from db.models.chain_anchor import ChainAnchor
    from db.models.operation import Operation

    roles = get_roles(actor)
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required to anchor the chain",
        )

    tenant_id_str = actor.get("tenant_id", "")
    tenant_id = UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID
    http_client: httpx.AsyncClient | None = getattr(request.app.state, "http_client", None)

    head = await get_latest_chain_hash(db, tenant_id)
    if head == GENESIS_HASH:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No sealed operations to anchor for this tenant.",
        )

    ops_count = (
        await db.execute(
            select(func.count())
            .select_from(Operation)
            .where(
                Operation.tenant_id == tenant_id,
                Operation.chain_hash.isnot(None),
            )
        )
    ).scalar_one()

    # Sign the chain head with the asymmetric key. Anchoring is fail-closed: an
    # unsigned anchor is worthless, so refuse if signing is unavailable.
    signature, key_version = await sign_operation_hash(
        head,
        vault_addr=settings.vault_addr,
        vault_token=settings.vault_dev_token,
        vault_key=settings.vault_transit_key,
        http_client=http_client,
    )
    if signature is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing service unavailable; cannot create a signed anchor.",
        )

    # Optional RFC 3161 timestamp over the chain head.
    tsa_token_b64: str | None = None
    if settings.tsa_enabled:
        tsa_result = await request_tsa_token(bytes.fromhex(head), http_client=http_client)
        if tsa_result:
            tsa_token_b64 = tsa_result.token_b64

    try:
        created_by = UUID(str(actor["sub"])) if actor.get("sub") else None
    except (ValueError, TypeError):
        created_by = None

    # Set id/created_at explicitly so the response does not depend on a DB
    # round-trip populating server-side defaults.
    from uuid import uuid4

    anchor_id = uuid4()
    created_at = datetime.now(UTC)
    anchor = ChainAnchor(
        id=anchor_id,
        tenant_id=tenant_id,
        chain_head_hash=head,
        operations_count=int(ops_count),
        signature=signature,
        signing_key_version=key_version,
        tsa_token=tsa_token_b64,
        created_by=created_by,
        created_at=created_at,
    )
    async with db.begin():
        db.add(anchor)
        await db.flush()

    logger.info(
        "audit.anchor.created",
        tenant_id=str(tenant_id),
        chain_head=head[:16] + "...",
        operations_count=int(ops_count),
        key_version=key_version,
        has_tsa=tsa_token_b64 is not None,
    )

    return ChainAnchorResponse(
        id=anchor_id,
        tenant_id=tenant_id,
        chain_head_hash=head,
        operations_count=int(ops_count),
        signing_key_version=key_version,
        has_tsa=tsa_token_b64 is not None,
        created_at=created_at,
    )
