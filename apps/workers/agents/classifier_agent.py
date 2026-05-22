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
from collections import Counter

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

# Rank for max() comparison — module-level constant, not recreated per task call.
_SEVERITY_RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}


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

            # Single O(n) pass for both highest-severity and per-level counts.
            severity_counts = Counter(f.severity for f in findings)
            highest_severity = max(
                severity_counts or ["low"],
                key=lambda s: _SEVERITY_RANK.get(s, 0),
            )
            classification_level = _SEVERITY_TO_LEVEL.get(highest_severity, "public")

            logger.info(
                "classifier_agent.classified",
                id=operation_id,
                level=classification_level,
                highest_severity=highest_severity,
                findings_count=len(findings),
                critical_count=severity_counts["critical"],
                high_count=severity_counts["high"],
                medium_count=severity_counts["medium"],
                low_count=severity_counts["low"],
                policy_version=operation.policy_version,
            )

    TASKS_TOTAL.labels(agent="classifier", status="success").inc()
