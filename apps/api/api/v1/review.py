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
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth_oidc import check_self_approval, require_reviewer
from core.constants import SENTINEL_ACTOR_ID
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


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _load_escalated_finding(
    finding_id: UUID,
    db: AsyncSession,
) -> tuple[Finding, Operation]:
    """Load a Finding and its Operation, asserting the operation is escalated.

    Raises 404 if the finding doesn't exist, 409 if the operation is not
    in 'escalated' state.  Extracted to eliminate the identical 13-line guard
    that previously appeared in both approve_finding and reject_finding.
    """
    result = await db.execute(
        select(Finding)
        .where(Finding.id == finding_id)
        .options(selectinload(Finding.operation))
    )
    finding: Finding | None = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    operation = finding.operation
    if operation.status != "escalated":
        raise HTTPException(
            status_code=409,
            detail=f"Operation status is '{operation.status}', expected 'escalated'",
        )
    return finding, operation


async def _load_document_previews(
    operation_ids: list[UUID],
    db: AsyncSession,
) -> dict[str, str]:
    """Bulk-load document previews for a list of operation IDs.

    Single query replaces the previous N+1 pattern in get_pending_reviews.
    Returns a mapping of operation_id (str) → first-200-chars of document text.
    """
    if not operation_ids:
        return {}

    str_ids = [str(oid) for oid in operation_ids]
    result = await db.execute(
        select(Outbox).where(
            Outbox.payload["operation_id"].as_string().in_(str_ids)
        )
    )
    rows = result.scalars().all()
    return {
        row.payload.get("operation_id", ""): row.payload.get("document_text", "")[:200]
        for row in rows
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/review/pending", response_model=PendingReviewResponse)
async def get_pending_reviews(
    _actor: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PendingReviewResponse:
    """Return escalated operations and their findings, paginated."""
    ops_result = await db.execute(
        select(Operation)
        .where(Operation.status == "escalated")
        .options(selectinload(Operation.findings))
    )
    operations = ops_result.scalars().all()

    preview_map = await _load_document_previews([op.id for op in operations], db)

    all_items: list[PendingFindingResponse] = []
    for op in operations:
        preview = preview_map.get(str(op.id), "")
        for finding in op.findings:
            all_items.append(
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

    total = len(all_items)
    items = all_items[offset : offset + limit]

    log.info("review.pending.listed", total=total, returned=len(items))
    return PendingReviewResponse(total=total, items=items)


@router.post("/review/{finding_id}/approve", status_code=status.HTTP_200_OK)
async def approve_finding(
    finding_id: UUID,
    body: ReviewDecisionRequest,
    actor: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve a finding: create a Redaction, advance operation if fully reviewed.

    All reads and writes happen in a single atomic transaction with a row-level
    lock on the Operation to prevent concurrent approval races.
    """
    finding, operation = await _load_escalated_finding(finding_id, db)

    # Use real reviewer UUID from the Keycloak JWT sub claim.
    # Falls back to SENTINEL_ACTOR_ID only if sub is missing (shouldn't happen).
    sub = actor.get("sub", "")
    reviewer_id = uuid.UUID(sub) if sub else SENTINEL_ACTOR_ID

    check_self_approval(str(operation.actor_id), actor)

    async with db.begin():
        # Re-fetch the operation under a row-level lock.
        # The pre-check in _load_escalated_finding runs WITHOUT a lock, so a
        # concurrent request could pass the status guard simultaneously.
        # Re-validating status AFTER acquiring the lock closes the TOCTOU window.
        locked_op_result = await db.execute(
            select(Operation)
            .where(Operation.id == operation.id)
            .with_for_update()
        )
        operation = locked_op_result.scalar_one()
        if operation.status != "escalated":
            raise HTTPException(
                status_code=409,
                detail=f"Operation status is '{operation.status}', expected 'escalated' (concurrent update)",
            )

        redaction = Redaction(
            finding_id=finding.id,
            operation_id=operation.id,
            redaction_type="mask",
            policy_version=operation.policy_version,
            approved_by=reviewer_id,
            approval_trace_id=operation.trace_id,
        )
        db.add(redaction)
        await db.flush()  # get the new row into the session snapshot

        # Check completion: count findings vs redactions in the same transaction
        total_findings = (await db.execute(
            select(func.count()).select_from(Finding)
            .where(Finding.operation_id == operation.id)
        )).scalar_one()

        total_redactions = (await db.execute(
            select(func.count()).select_from(Redaction)
            .where(Redaction.operation_id == operation.id)
        )).scalar_one()

        if total_redactions >= total_findings:
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
    finding, operation = await _load_escalated_finding(finding_id, db)

    sub = actor.get("sub", "")
    reviewer_id = uuid.UUID(sub) if sub else SENTINEL_ACTOR_ID

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
