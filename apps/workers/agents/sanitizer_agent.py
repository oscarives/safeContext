"""sanitizer_agent — Dramatiq worker that redacts detected spans.

Pipeline position: 2nd stage.
  process_scan → process_sanitize → process_audit

Idempotency guarantee:
  Checks whether redactions already exist for this operation before writing.
  Re-delivery is therefore safe — existing redactions are not duplicated.
"""

from __future__ import annotations

import asyncio
import uuid

import dramatiq
import structlog
from sqlalchemy import select

from db.models.finding import Finding as FindingModel
from db.models.operation import Operation
from db.models.redaction import Redaction

from workers.core.db import get_session
from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS

logger = structlog.get_logger(__name__)


@dramatiq.actor(
    queue_name="safecontext_sanitize",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_sanitize(operation_id: str) -> None:
    asyncio.run(_process_sanitize_async(operation_id))


async def _process_sanitize_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="sanitizer").time():
        async with get_session() as session:
            # ── Idempotency check ────────────────────────────────────────────
            existing = await session.execute(
                select(Redaction).where(Redaction.operation_id == op_uuid).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                logger.info("sanitizer_agent.skip_idempotent", id=operation_id)
                TASKS_TOTAL.labels(agent="sanitizer", status="skipped").inc()
                return

            # ── Fetch operation and its findings ─────────────────────────────
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("sanitizer_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="sanitizer", status="failure").inc()
                return

            findings_result = await session.execute(
                select(FindingModel).where(FindingModel.operation_id == op_uuid)
            )
            findings = findings_result.scalars().all()

            if not findings:
                logger.info(
                    "sanitizer_agent.no_findings",
                    id=operation_id,
                    proceeding_to="audit",
                )
            else:
                for f in findings:
                    redaction_type = _severity_to_redaction_type(f.severity)
                    redaction = Redaction(
                        finding_id=f.id,
                        operation_id=op_uuid,
                        redaction_type=redaction_type,
                        policy_version=operation.policy_version,
                    )
                    session.add(redaction)
                    logger.debug(
                        "sanitizer_agent.redaction",
                        finding_id=str(f.id),
                        type=redaction_type,
                    )

            logger.info(
                "sanitizer_agent.done",
                id=operation_id,
                redactions=len(findings),
            )

    from workers.agents.auditor_agent import process_audit
    process_audit.send(operation_id)
    logger.info("sanitizer_agent.enqueued_audit", id=operation_id)
    TASKS_TOTAL.labels(agent="sanitizer", status="success").inc()


def _severity_to_redaction_type(severity: str) -> str:
    """Map finding severity to redaction strategy."""
    return {
        "critical": "mask",
        "high": "mask",
        "medium": "mask",
        "low": "replace",
    }.get(severity, "mask")
