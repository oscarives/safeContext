"""reviewer_agent — Dramatiq worker that handles escalated operations.

Pipeline position: side-branch when detector_agent sets status='escalated'.
  process_scan (escalated) → process_review

This worker does NOT alter the operation status — unblocking escalated
operations is a human action via the UI (E2.6). It logs structured audit
data and can send notifications (log-level for now).

ADR-007: The reviewer_agent is intentionally thin; business logic lives in OPA.
"""

from __future__ import annotations

import asyncio
import uuid

import dramatiq
import structlog
from sqlalchemy import select

from db.models.finding import Finding as FindingModel
from db.models.operation import Operation

from workers.core.db import get_session
from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS

logger = structlog.get_logger(__name__)


@dramatiq.actor(
    queue_name="safecontext_review",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_review(operation_id: str) -> None:
    asyncio.run(_process_review_async(operation_id))


async def _process_review_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="reviewer").time():
        async with get_session() as session:
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("reviewer_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="reviewer", status="failure").inc()
                return

            if operation.status != "escalated":
                logger.info(
                    "reviewer_agent.unexpected_status",
                    id=operation_id,
                    status=operation.status,
                )
                TASKS_TOTAL.labels(agent="reviewer", status="skipped").inc()
                return

            findings_result = await session.execute(
                select(FindingModel).where(FindingModel.operation_id == op_uuid)
            )
            findings = findings_result.scalars().all()

            critical_findings = [f for f in findings if f.severity == "critical"]
            high_findings = [f for f in findings if f.severity == "high"]

            # Structured audit log — consumed by OTel collector / SIEM
            logger.warning(
                "reviewer_agent.escalated_operation",
                event="operation_escalated",
                operation_id=operation_id,
                actor_id=str(operation.actor_id),
                actor_type=operation.actor_type,
                document_id=str(operation.document_id),
                policy_version=operation.policy_version,
                findings_total=len(findings),
                critical_findings=len(critical_findings),
                high_findings=len(high_findings),
                critical_detectors=[f.detector for f in critical_findings],
                requires_human_review=True,
            )

    TASKS_TOTAL.labels(agent="reviewer", status="success").inc()
