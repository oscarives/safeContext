"""detector_agent — Dramatiq worker that runs PII/secret detection.

Pipeline position: 1st stage.
  outbox → process_scan → [escalated | process_sanitize]

Idempotency guarantee:
  If the operation's status is not 'pending', the task exits immediately
  without side-effects. Re-delivery is therefore safe.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import dramatiq
import structlog
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from sqlalchemy import select, update

# DB models are available via PYTHONPATH=/workspace in Docker
# (Dockerfile: COPY apps/api/db/ ./db/).
# For local dev: export PYTHONPATH=<repo>/apps/api:$PYTHONPATH
from db.models.finding import Finding as FindingModel
from db.models.operation import Operation
from db.models.outbox import Outbox

from workers.config import settings
from workers.core.db import get_session
from workers.core.metrics import FINDINGS_TOTAL, TASKS_TOTAL, TASK_DURATION_SECONDS
from workers.core.opa_client import OPAUnavailableError, opa_client
from workers.ml.presidio_detector import PresidioDetector
from workers.ml.regex_detector import RegexDetector

# Module-level singletons — neither detector holds per-task mutable state.
# RegexDetector is instantiated alongside PresidioDetector so both are ready
# before any task arrives (T4: regex pre-ML layer).
_regex_detector = RegexDetector()
_detector = PresidioDetector()


def _merge_findings(regex: list, presidio: list) -> list:
    """Merge regex and Presidio findings, deduplicating by span overlap.

    Regex findings are authoritative for any span they cover. Presidio
    findings that overlap with an existing regex finding are dropped to
    avoid duplicate annotations on the same text range.

    Args:
        regex:   Findings from RegexDetector (higher-confidence, deterministic).
        presidio: Findings from PresidioDetector (NER / ML-based).

    Returns:
        Combined, span-start–sorted list with no overlapping entries.
    """
    merged = list(regex)
    for pf in presidio:
        overlaps = any(
            max(rf.span_start, pf.span_start) < min(rf.span_end, pf.span_end)
            for rf in regex
        )
        if not overlaps:
            merged.append(pf)
    return sorted(merged, key=lambda f: f.span_start)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Broker setup — configured once per process via settings.
# When loaded via workers.main, the broker is already set. When this module
# is imported standalone (e.g. during tests), we initialise a default broker.
# ---------------------------------------------------------------------------

try:
    _current_broker = dramatiq.get_broker()
    # Use isinstance() — not a string comparison — so renaming or subclassing StubBroker
    # doesn't silently break this check.
    if isinstance(_current_broker, StubBroker):
        _broker = RedisBroker(url=settings.redis_url)
        dramatiq.set_broker(_broker)
except RuntimeError:
    # Dramatiq raises RuntimeError when no broker has been configured yet.
    _broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(_broker)


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------


@dramatiq.actor(
    queue_name="safecontext_scan",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_scan(operation_id: str) -> None:
    """Detect PII/secrets in the document linked to *operation_id*."""
    asyncio.run(_process_scan_async(operation_id))


async def _process_scan_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="detector").time():
        # ── 3. Obtain OPA policy BEFORE opening DB session ───────────────────
        # Cache lookup is free (in-memory); live fetch avoids holding a DB
        # connection idle while waiting for OPA (up to 5 s timeout).
        policy: dict[str, Any] = await opa_client.get_policy("base")

        async with get_session() as session:
            # ── 1. Idempotency check ─────────────────────────────────────────
            result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = result.scalar_one_or_none()

            if operation is None:
                logger.error("detector_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="detector", status="failure").inc()
                return

            if operation.status != "pending":
                logger.info(
                    "detector_agent.skip_idempotent",
                    id=operation_id,
                    status=operation.status,
                )
                TASKS_TOTAL.labels(agent="detector", status="skipped").inc()
                return

            # ── 2. Fetch document from outbox payload ────────────────────────
            outbox_result = await session.execute(
                select(Outbox).where(
                    Outbox.payload["operation_id"].as_string() == operation_id
                )
            )
            outbox_entry: Outbox | None = outbox_result.scalars().first()

            if outbox_entry is None:
                logger.error("detector_agent.outbox_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="detector", status="failure").inc()
                return

            payload: dict = outbox_entry.payload
            document_text: str = payload.get("document_text", "")

            # ── 4. Run detectors (T4: regex pre-ML + Presidio NER) ───────────
            regex_findings = await _regex_detector.detect(document_text, policy)
            presidio_findings = await _detector.detect(document_text, policy)
            findings = _merge_findings(regex_findings, presidio_findings)

            logger.info(
                "detector_agent.findings",
                id=operation_id,
                count=len(findings),
                regex_count=len(regex_findings),
                presidio_count=len(presidio_findings),
            )

            # ── 5. Persist findings ──────────────────────────────────────────
            for f in findings:
                db_finding = FindingModel(
                    operation_id=op_uuid,
                    detector=f.detector,
                    rule_id=f.rule_id,
                    span_start=f.span_start,
                    span_end=f.span_end,
                    confidence=f.confidence,
                    severity=f.severity,
                    explanation=f.explanation,
                )
                session.add(db_finding)
                FINDINGS_TOTAL.labels(
                    entity_type=f.explanation.get("entity_type", "UNKNOWN"),
                    severity=f.severity,
                ).inc()

            # ── 6. OPA: decide whether to escalate ───────────────────────────
            requires_review: bool = False
            if findings:
                findings_payload = [
                    {
                        "entity_type": f.explanation.get("entity_type", "UNKNOWN"),
                        "severity": f.severity,
                        "confidence": f.confidence,
                    }
                    for f in findings
                ]
                try:
                    result_data = await opa_client.evaluate(
                        "safecontext/policy/operation_requires_review",
                        {"findings": findings_payload},
                    )
                    requires_review = bool(result_data)
                except OPAUnavailableError as exc:
                    logger.warning(
                        "detector_agent.opa_review_check_failed", error=str(exc)
                    )
                    # Conservative: escalate if OPA is unavailable so findings
                    # are not silently passed without human review.
                    requires_review = any(f.severity == "critical" for f in findings)

            # ── 7. Update status and enqueue next stage ──────────────────────
            new_status = "escalated" if requires_review else "pending"
            await session.execute(
                update(Operation)
                .where(Operation.id == op_uuid)
                .values(status=new_status)
            )

            # ── 8. Mark outbox entry processed ───────────────────────────────
            await session.execute(
                update(Outbox)
                .where(Outbox.id == outbox_entry.id)
                .values(processed=True)
            )

        # Enqueue sanitize outside of session (commit already happened)
        if not requires_review:
            from workers.agents.sanitizer_agent import process_sanitize
            process_sanitize.send(operation_id)
            logger.info("detector_agent.enqueued_sanitize", id=operation_id)
        else:
            from workers.agents.reviewer_agent import process_review
            process_review.send(operation_id)
            logger.info("detector_agent.enqueued_review", id=operation_id)

    TASKS_TOTAL.labels(agent="detector", status="success").inc()
