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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from core.logging import get_logger
from db.models.finding import Finding
from db.models.operation import Operation
from db.session import get_db
from schemas.audit import (
    ArtifactAuditSchema,
    AuditExportResponse,
    FindingAuditSchema,
    RedactionAuditSchema,
)

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

    logger.info(
        "audit.export",
        trace_id=str(trace_id),
        requested_by=actor_id,
        findings_count=len(findings),
        redactions_count=len(redactions),
        artifacts_count=len(artifacts),
    )

    return AuditExportResponse(
        trace_id=trace_id,
        exported_at=exported_at,
        operation=operation_dict,
        findings=findings,
        redactions=redactions,
        artifacts=artifacts,
        hmac_signature=signature,
    )


class VerificationKeyResponse(BaseModel):
    algorithm: str
    key_hint: str
    instructions: str


@router.get("/audit/verification-key", response_model=VerificationKeyResponse, tags=["audit"])
async def verification_key() -> VerificationKeyResponse:
    """
    Return the public HMAC verification hint and usage instructions.

    No authentication required — this is informational metadata only.
    The secret key itself is never exposed; only the first 8 characters
    are returned as an identifier hint.
    """
    key_hint = settings.api_secret_key[:8] + "..."
    instructions = (
        "Para verificar la integridad de un export de auditoría:\n"
        "\n"
        "import hashlib, hmac, json\n"
        "\n"
        "def verify_export(export: dict, secret: str) -> bool:\n"
        "    received_sig = export.pop('hmac_signature')\n"
        "    data = json.dumps(export, sort_keys=True, default=str).encode()\n"
        "    expected = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()\n"
        "    return hmac.compare_digest(received_sig, expected)\n"
        "\n"
        "La clave completa debe obtenerse del administrador del sistema."
    )
    logger.info("audit.verification_key.requested")
    return VerificationKeyResponse(
        algorithm="HMAC-SHA256",
        key_hint=key_hint,
        instructions=instructions,
    )


@router.get("/audit/{trace_id}", response_model=AuditExportResponse, tags=["audit"])
async def audit_export_endpoint(
    trace_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditExportResponse:
    """
    Return full audit evidence for the operation identified by trace_id.

    The response payload is signed with HMAC-SHA256 so consumers can verify
    integrity without trusting the transport layer.
    """
    actor_id: str = str(getattr(request.state, "actor_id", "anonymous"))
    result = await get_audit_export(trace_id, db, actor_id=actor_id)
    if result is None:
        raise HTTPException(status_code=404, detail="trace_id not found")
    return result
