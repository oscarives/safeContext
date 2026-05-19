"""classifier_agent — Dramatiq worker that assigns a sensitivity level.

Pipeline position: runs after detection (called by reviewer_agent or on demand).

Classification logic (mirrors NIST / common DLP conventions):
  critical finding  → "restricted"
  high finding      → "confidential"
  medium finding    → "internal"
  low / no finding  → "public"

The classification result is stored as a structured JSON audit log entry; it
is also surfaced on the Operation row via a hypothetical metadata JSONB column
(future migration). For now it is persisted as a structured log entry and
can be added to operations.metadata in a later migration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import dramatiq

from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS

logger = logging.getLogger(__name__)

# Severity → classification level
_SEVERITY_TO_LEVEL: dict[str, str] = {
    "critical": "restricted",
    "high": "confidential",
    "medium": "internal",
    "low": "public",
}

_LEVEL_RANK: dict[str, int] = {
    "restricted": 4,
    "confidential": 3,
    "internal": 2,
    "public": 1,
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
    from sqlalchemy import select

    from workers.db import get_session

    import sys

    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api")
    )

    from db.models.operation import Operation
    from db.models.finding import Finding as FindingModel

    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="classifier").time():
        async with get_session() as session:
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("classifier_agent.operation_not_found id=%s", operation_id)
                TASKS_TOTAL.labels(agent="classifier", status="failure").inc()
                return

            findings_result = await session.execute(
                select(FindingModel).where(FindingModel.operation_id == op_uuid)
            )
            findings = findings_result.scalars().all()

            # Determine highest severity
            highest_severity: str = "low"
            highest_rank: int = 0
            for f in findings:
                rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                    f.severity, 0
                )
                if rank > highest_rank:
                    highest_rank = rank
                    highest_severity = f.severity

            classification_level: str = _SEVERITY_TO_LEVEL.get(
                highest_severity, "public"
            )

            structured_result = {
                "operation_id": operation_id,
                "classification_level": classification_level,
                "justification": {
                    "highest_severity": highest_severity,
                    "findings_count": len(findings),
                    "critical_count": sum(
                        1 for f in findings if f.severity == "critical"
                    ),
                    "high_count": sum(1 for f in findings if f.severity == "high"),
                    "medium_count": sum(1 for f in findings if f.severity == "medium"),
                    "low_count": sum(1 for f in findings if f.severity == "low"),
                },
                "policy_version": operation.policy_version,
            }

            logger.info(
                "classifier_agent.classified id=%s level=%s highest_severity=%s",
                operation_id,
                classification_level,
                highest_severity,
                extra={"classification": structured_result},
            )

    TASKS_TOTAL.labels(agent="classifier", status="success").inc()
    return structured_result
