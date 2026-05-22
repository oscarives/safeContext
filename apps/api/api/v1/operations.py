"""Operations list endpoint — GET /v1/operations.

Returns a paginated, filterable list of operations with aggregated status counts.
Used by the Dashboard and Audit page for recent activity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import require_auth
from db.models.finding import Finding
from db.models.operation import Operation
from db.session import get_db

router = APIRouter(tags=["operations"])
log = structlog.get_logger(__name__)


# ── Response schemas ──────────────────────────────────────────────────────────


class OperationItem(BaseModel):
    id: UUID
    trace_id: UUID
    actor_id: UUID
    actor_type: str
    artifact_digest: str
    policy_version: str
    status: str
    findings_count: int
    created_at: datetime
    completed_at: datetime | None


class OperationsListResponse(BaseModel):
    total: int
    items: list[OperationItem]
    # Aggregated counts across ALL matching operations (not just the current page).
    # Used by the Dashboard to display status metrics without a second request.
    total_pending: int = 0
    total_escalated: int = 0
    total_completed: int = 0
    total_rejected: int = 0


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/operations", response_model=OperationsListResponse)
async def list_operations(
    _actor: Annotated[dict, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    from_date: str | None = Query(default=None, description="ISO 8601 start date"),
    to_date: str | None = Query(default=None, description="ISO 8601 end date"),
    actor_id: str | None = Query(default=None, description="UUID of the actor"),
) -> OperationsListResponse:
    """
    Return a paginated list of operations with optional filters and aggregated counts.

    Any authenticated user can access this endpoint.
    The response includes per-status counts for the Dashboard metrics panel.
    """
    # Clamp limit to 100
    limit = min(limit, 100)

    # Parse and validate date inputs — raise 422 on bad format
    dt_from: datetime | None = None
    dt_to: datetime | None = None
    if from_date is not None:
        try:
            dt_from = datetime.fromisoformat(from_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid from_date format: {from_date!r}. Use ISO 8601.",
            ) from exc
    if to_date is not None:
        try:
            dt_to = datetime.fromisoformat(to_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid to_date format: {to_date!r}. Use ISO 8601.",
            ) from exc

    # Parse actor_id UUID if provided — supports "me" as an alias for the current user
    actor_uuid: UUID | None = None
    if actor_id == "me":
        sub = _actor.get("sub", "")
        if sub:
            try:
                actor_uuid = UUID(sub)
            except ValueError:
                pass  # invalid sub — no filter applied
    elif actor_id is not None:
        try:
            actor_uuid = UUID(actor_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid actor_id format: {actor_id!r}. Must be a UUID or 'me'.",
            ) from exc

    # Build base filters (reused for both stats and items queries)
    filters = []
    if status_filter is not None:
        filters.append(Operation.status == status_filter)
    if dt_from is not None:
        filters.append(Operation.created_at >= dt_from)
    if dt_to is not None:
        filters.append(Operation.created_at <= dt_to)
    if actor_uuid is not None:
        filters.append(Operation.actor_id == actor_uuid)

    # ── Aggregated stats — single query replacing the separate COUNT(*) ────────
    # Uses conditional COUNT so we get total + per-status breakdown in one round-trip.
    stats_stmt = select(
        func.count().label("total"),
        func.count(case((Operation.status == "pending", 1))).label("total_pending"),
        func.count(case((Operation.status == "escalated", 1))).label("total_escalated"),
        func.count(case((Operation.status == "completed", 1))).label("total_completed"),
        func.count(case((Operation.status == "rejected", 1))).label("total_rejected"),
    ).select_from(Operation)
    if filters:
        stats_stmt = stats_stmt.where(*filters)

    stats_row = (await db.execute(stats_stmt)).one()
    total: int = stats_row.total

    # ── Paginated items ───────────────────────────────────────────────────────

    # Subquery: findings count per operation
    findings_subq = (
        select(Finding.operation_id, func.count(Finding.id).label("findings_count"))
        .group_by(Finding.operation_id)
        .subquery()
    )

    items_stmt = (
        select(Operation, func.coalesce(findings_subq.c.findings_count, 0).label("findings_count"))
        .outerjoin(findings_subq, Operation.id == findings_subq.c.operation_id)
        .order_by(Operation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if filters:
        items_stmt = items_stmt.where(*filters)

    rows = await db.execute(items_stmt)
    results = rows.all()

    items: list[OperationItem] = [
        OperationItem(
            id=op.id,
            trace_id=op.trace_id,
            actor_id=op.actor_id,
            actor_type=op.actor_type,
            artifact_digest=op.artifact_digest,
            policy_version=op.policy_version,
            status=op.status,
            findings_count=int(findings_count),
            created_at=op.created_at,
            completed_at=op.completed_at,
        )
        for op, findings_count in results
    ]

    log.info(
        "operations.listed",
        total=total,
        returned=len(items),
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )

    return OperationsListResponse(
        total=total,
        items=items,
        total_pending=stats_row.total_pending,
        total_escalated=stats_row.total_escalated,
        total_completed=stats_row.total_completed,
        total_rejected=stats_row.total_rejected,
    )
