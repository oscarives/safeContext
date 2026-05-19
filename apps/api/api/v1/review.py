"""Human review endpoints — E2.6.

GET  /v1/review/pending              — list escalated findings awaiting review
POST /v1/review/{finding_id}/approve — approve a finding, register redaction
POST /v1/review/{finding_id}/reject  — reject a finding, mark operation rejected
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth_oidc import require_reviewer
from db.models.finding import Finding
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.models.redaction import Redaction
from db.session import get_db

log = structlog.get_logger()
router = APIRouter(tags=["review"])


# ── Request / Response schemas ────────────────────────────────────────────────


class ReviewDecisionRequest(BaseModel):
    justification: str


class PendingFindingResponse(BaseModel):
    operation_id: UUID
    trace_id: UUID
    finding_id: UUID
    detector: str
    rule_id: str
    confidence: float
    severity: str
    span_start: int
    span_end: int
    explanation: dict[str, Any]
    document_preview: str
    created_at: datetime


class PendingReviewResponse(BaseModel):
    total: int
    items: list[PendingFindingResponse]


# ── Helper ────────────────────────────────────────────────────────────────────


async def _load_document_preview(operation_id: UUID, db: AsyncSession) -> str:
    """Return first 200 chars of the document stored in the outbox payload."""
    result = await db.execute(
        select(Outbox).where(Outbox.payload["operation_id"].as_string() == str(operation_id))
    )
    outbox_entry = result.scalar_one_or_none()
    if outbox_entry is None:
        return ""
    doc: str = outbox_entry.payload.get("document", "")
    return doc[:200]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/review/pending", response_model=PendingReviewResponse)
async def get_pending_reviews(
    _actor: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> PendingReviewResponse:
    """Return all operations with status='escalated' and their findings."""
    ops_result = await db.execute(
        select(Operation)
        .where(Operation.status == "escalated")
        .options(selectinload(Operation.findings))
    )
    operations = ops_result.scalars().all()

    items: list[PendingFindingResponse] = []
    for op in operations:
        preview = await _load_document_preview(op.id, db)
        for finding in op.findings:
            items.append(
                PendingFindingResponse(
                    operation_id=op.id,
                    trace_id=op.trace_id,
                    finding_id=finding.id,
                    detector=finding.detector,
                    rule_id=finding.rule_id,
                    confidence=finding.confidence,
                    severity=finding.severity,
                    span_start=finding.span_start,
                    span_end=finding.span_end,
                    explanation=finding.explanation,
                    document_preview=preview,
                    created_at=op.created_at,
                )
            )

    log.info("review.pending.listed", count=len(items))
    return PendingReviewResponse(total=len(items), items=items)


@router.post("/review/{finding_id}/approve", status_code=status.HTTP_200_OK)
async def approve_finding(
    finding_id: UUID,
    body: ReviewDecisionRequest,
    actor: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve a finding: create a Redaction, advance operation if fully reviewed."""
    # Load finding and its operation
    finding_result = await db.execute(
        select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.operation))
    )
    finding: Finding | None = finding_result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    operation = finding.operation
    if operation.status != "escalated":
        raise HTTPException(
            status_code=409,
            detail=f"Operation status is '{operation.status}', expected 'escalated'",
        )

    # Use a fixed reviewer UUID for now (replaced by real identity in F4)
    reviewer_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    redaction = Redaction(
        finding_id=finding.id,
        operation_id=operation.id,
        redaction_type="mask",
        policy_version=operation.policy_version,
        approved_by=reviewer_id,
        approval_trace_id=operation.trace_id,
    )

    async with db.begin():
        db.add(redaction)

    # Reload all findings for this operation to check completion
    all_findings_result = await db.execute(
        select(Finding).where(Finding.operation_id == operation.id)
    )
    all_findings = all_findings_result.scalars().all()
    all_finding_ids = {f.id for f in all_findings}

    # Check existing redactions
    from db.models.redaction import Redaction as RedactionModel

    redactions_result = await db.execute(
        select(RedactionModel).where(RedactionModel.operation_id == operation.id)
    )
    existing_redactions = redactions_result.scalars().all()
    redacted_finding_ids = {r.finding_id for r in existing_redactions}

    # If all findings have a redaction → mark completed
    if all_finding_ids.issubset(redacted_finding_ids):
        async with db.begin():
            operation.status = "completed"
            operation.completed_at = datetime.now(UTC)
            db.add(operation)

    log.info(
        "review.finding.approved",
        finding_id=str(finding_id),
        trace_id=str(operation.trace_id),
        actor_id=str(reviewer_id),
        justification=body.justification,
    )

    return {"trace_id": str(operation.trace_id), "status": "approved"}


@router.post("/review/{finding_id}/reject", status_code=status.HTTP_200_OK)
async def reject_finding(
    finding_id: UUID,
    body: ReviewDecisionRequest,
    actor: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reject a finding: mark the operation as 'rejected'."""
    finding_result = await db.execute(
        select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.operation))
    )
    finding: Finding | None = finding_result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    operation = finding.operation
    if operation.status != "escalated":
        raise HTTPException(
            status_code=409,
            detail=f"Operation status is '{operation.status}', expected 'escalated'",
        )

    reviewer_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    async with db.begin():
        operation.status = "rejected"
        operation.completed_at = datetime.now(UTC)
        db.add(operation)

    log.info(
        "review.finding.rejected",
        finding_id=str(finding_id),
        trace_id=str(operation.trace_id),
        actor_id=str(reviewer_id),
        justification=body.justification,
    )

    return {"trace_id": str(operation.trace_id), "status": "rejected"}
