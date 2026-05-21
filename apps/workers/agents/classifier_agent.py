"""classifier_agent — Dramatiq worker that assigns a sensitivity level.

Pipeline position: runs after detection (called by reviewer_agent or on demand).

Classification logic (mirrors NIST / common DLP conventions):
  critical finding  → "restricted"
  high finding      → "confidential"
  medium finding    → "internal"
  low / no finding  → "public"
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

# Severity → classification level
_SEVERITY_TO_LEVEL: dict[str, str] = {
    "critical": "restricted",
    "high": "confidential",
    "medium": "internal",
    "low": "public",
}


@dramatiq.actor(
    queue_name="safecontext_classify",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_classify(operation_id: str) -> None:
    asyncio.run(_process_classify_async(operation_id))


async def _process_classify_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="classifier").time():
        async with get_session() as session:
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("classifier_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="classifier", status="failure").inc()
                return

            findings_result = await session.execute(
                select(FindingModel).where(FindingModel.operation_id == op_uuid)
            )
            findings = findings_result.scalars().all()

            # Determine highest severity
            _RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            highest_severity = max(
                (f.severity for f in findings),
                key=lambda s: _RANK.get(s, 0),
                default="low",
            )
            classification_level = _SEVERITY_TO_LEVEL.get(highest_severity, "public")

            logger.info(
                "classifier_agent.classified",
                id=operation_id,
                level=classification_level,
                highest_severity=highest_severity,
                findings_count=len(findings),
                critical_count=sum(1 for f in findings if f.severity == "critical"),
                high_count=sum(1 for f in findings if f.severity == "high"),
                medium_count=sum(1 for f in findings if f.severity == "medium"),
                low_count=sum(1 for f in findings if f.severity == "low"),
                policy_version=operation.policy_version,
            )

    TASKS_TOTAL.labels(agent="classifier", status="success").inc()
