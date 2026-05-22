"""rescan_agent — Dramatiq worker that re-analyses sanitized text for residual PII.

T3: Rescan post-sanitización.

Pipeline position: 3rd stage (triggered by sanitizer_agent after redaction).
  process_sanitize → rescan_operation → [escalated | completed]

Purpose:
  After the sanitizer redacts detected spans, edge-cases can leave residual PII
  in the sanitized text (e.g. a regex matched only the first occurrence of an
  email, or the sanitizer replaced the wrong span). This agent re-runs the full
  detector stack on the sanitized text and, if anything leaks through, escalates
  the operation for human review.

Idempotency:
  The agent checks whether any post-sanitization Finding already exists for
  this operation before scanning. Re-delivery is therefore safe.
"""

from __future__ import annotations

import asyncio
import uuid

import dramatiq
import structlog
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from sqlalchemy import select, update

from db.models.finding import Finding as FindingModel
from db.models.operation import Operation

from workers.config import settings
from workers.core.db import get_session
from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS
from workers.ml.presidio_detector import PresidioDetector
from workers.ml.regex_detector import RegexDetector

# Re-use the merge helper from detector_agent to keep deduplication logic DRY.
from workers.agents.detector_agent import _merge_findings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Detector singletons — same pattern as detector_agent.
# ---------------------------------------------------------------------------

_regex_detector = RegexDetector()
_presidio_detector = PresidioDetector()

# ---------------------------------------------------------------------------
# Broker setup — mirrors detector_agent / sanitizer_agent bootstrap.
# ---------------------------------------------------------------------------

try:
    _current_broker = dramatiq.get_broker()
    if isinstance(_current_broker, StubBroker):
        _broker = RedisBroker(url=settings.redis_url)
        dramatiq.set_broker(_broker)
except RuntimeError:
    _broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(_broker)


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------


@dramatiq.actor(
    queue_name="safecontext_rescan",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def rescan_operation(operation_id: str) -> None:
    """Re-scan sanitized document text for residual PII/secrets."""
    asyncio.run(_rescan_operation_async(operation_id))


async def _rescan_operation_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="rescan").time():
        async with get_session() as session:
            # ── Fetch operation ──────────────────────────────────────────────
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.warning("rescan_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="rescan", status="failure").inc()
                return

            if not operation.sanitized_text:
                logger.info("rescan_agent.no_sanitized_text", id=operation_id)
                TASKS_TOTAL.labels(agent="rescan", status="skipped").inc()
                return

            # ── Idempotency check ────────────────────────────────────────────
            # Look for any existing post-sanitization finding for this operation.
            # We identify them by the is_post_sanitization flag stored in explanation.
            existing_result = await session.execute(
                select(FindingModel)
                .where(
                    FindingModel.operation_id == op_uuid,
                    FindingModel.explanation["is_post_sanitization"].as_boolean() == True,  # noqa: E712
                )
                .limit(1)
            )
            if existing_result.scalar_one_or_none() is not None:
                logger.info("rescan_agent.skip_idempotent", id=operation_id)
                TASKS_TOTAL.labels(agent="rescan", status="skipped").inc()
                return

            # ── Run detectors on sanitized text ──────────────────────────────
            # Use the same policy channel as the original scan if available.
            # For now we use a permissive policy (no score_threshold override)
            # so that even low-confidence residuals are surfaced.
            policy: dict = {}

            sanitized_text: str = operation.sanitized_text

            regex_findings = await _regex_detector.detect(sanitized_text, policy)
            presidio_findings = await _presidio_detector.detect(sanitized_text, policy)
            findings = _merge_findings(regex_findings, presidio_findings)

            logger.info(
                "rescan_agent.scan_complete",
                id=operation_id,
                residual_count=len(findings),
                regex_count=len(regex_findings),
                presidio_count=len(presidio_findings),
            )

            if findings:
                # ── Persist post-sanitization findings ───────────────────────
                for f in findings:
                    db_finding = FindingModel(
                        operation_id=op_uuid,
                        detector=f.detector,
                        rule_id=f.rule_id,
                        span_start=f.span_start,
                        span_end=f.span_end,
                        confidence=f.confidence,
                        severity=f.severity,
                        explanation={
                            **f.explanation,
                            "is_post_sanitization": True,
                        },
                    )
                    session.add(db_finding)

                # ── Escalate operation for human review ───────────────────────
                # "escalated" is the only status that triggers reviewer_agent.
                # We update only when not already escalated or rejected (those
                # states are terminal and must not be overwritten by automation).
                if operation.status not in ("escalated", "rejected", "approved"):
                    await session.execute(
                        update(Operation)
                        .where(Operation.id == op_uuid)
                        .values(status="escalated")
                    )
                    logger.warning(
                        "rescan_agent.residual_pii_escalated",
                        id=operation_id,
                        count=len(findings),
                    )

                TASKS_TOTAL.labels(agent="rescan", status="escalated").inc()

                # Enqueue reviewer outside session (commit already happened on exit)
                # Imported lazily to avoid circular-import issues at module load time.
                from workers.agents.reviewer_agent import process_review
                process_review.send(operation_id)
                logger.info("rescan_agent.enqueued_review", id=operation_id)

            else:
                # ── Mark complete when sanitized text is clean ────────────────
                # Only advance from "pending" (the status set after scan→sanitize
                # path). We never overwrite escalated/approved/rejected.
                if operation.status == "pending":
                    await session.execute(
                        update(Operation)
                        .where(Operation.id == op_uuid)
                        .values(status="completed")
                    )
                logger.info("rescan_agent.clean", id=operation_id)
                TASKS_TOTAL.labels(agent="rescan", status="success").inc()
