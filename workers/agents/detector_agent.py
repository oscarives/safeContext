"""detector_agent — Dramatiq worker that runs PII/secret detection.

Pipeline position: 1st stage.
  outbox → process_scan → [escalated | process_sanitize]

Idempotency guarantee:
  If the operation's status is not 'pending', the task exits immediately
  without side-effects. Re-delivery is therefore safe.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from workers.core.metrics import FINDINGS_TOTAL, TASKS_TOTAL, TASK_DURATION_SECONDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Broker setup — configured once per process via REDIS_URL env var.
# When loaded via workers.main, the broker is already set. When this module
# is imported standalone (e.g. during tests), we initialise a default broker.
# ---------------------------------------------------------------------------

_redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

try:
    _current_broker = dramatiq.get_broker()
    # Only replace if it's the default StubBroker (no real broker configured)
    if _current_broker.__class__.__name__ == "StubBroker":
        broker = RedisBroker(url=_redis_url)
        dramatiq.set_broker(broker)
except Exception:
    broker = RedisBroker(url=_redis_url)
    dramatiq.set_broker(broker)


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
    """Detect PII/secrets in the document linked to *operation_id*.

    Runs the synchronous wrapper around the async implementation so that
    Dramatiq (which is thread-based) can execute async code correctly.
    """
    asyncio.run(_process_scan_async(operation_id))


async def _process_scan_async(operation_id: str) -> None:
    import httpx
    from sqlalchemy import select, update

    from workers.core.db import get_session
    from workers.ml.presidio_detector import PresidioDetector

    # Lazy imports of DB models to avoid circular deps at module load
    import sys  # noqa: E401

    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api")
    )

    from db.models.operation import Operation
    from db.models.finding import Finding as FindingModel
    from db.models.outbox import Outbox

    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="detector").time():
        async with get_session() as session:
            # ── 1. Idempotency check ─────────────────────────────────────────
            result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = result.scalar_one_or_none()

            if operation is None:
                logger.error("detector_agent.operation_not_found id=%s", operation_id)
                TASKS_TOTAL.labels(agent="detector", status="failure").inc()
                return

            if operation.status != "pending":
                logger.info(
                    "detector_agent.skip_idempotent id=%s status=%s",
                    operation_id,
                    operation.status,
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
                logger.error("detector_agent.outbox_not_found id=%s", operation_id)
                TASKS_TOTAL.labels(agent="detector", status="failure").inc()
                return

            payload: dict = outbox_entry.payload
            document_text: str = payload.get("document_text", "")

            # ── 3. Obtain OPA policy for this operation ──────────────────────
            opa_url: str = os.environ.get("OPA_URL", "http://opa:8181")
            policy: dict[str, Any] = {}
            try:
                async with httpx.AsyncClient(timeout=5.0) as http:
                    resp = await http.get(
                        f"{opa_url}/v1/data/safecontext/policy",
                        params={"input": "{}"},
                    )
                    if resp.status_code == 200:
                        policy = resp.json().get("result", {})
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "detector_agent.opa_unavailable error=%s using_defaults=true", exc
                )

            # ── 4. Run detector ──────────────────────────────────────────────
            detector = PresidioDetector()
            findings = await detector.detect(document_text, policy)

            logger.info(
                "detector_agent.findings id=%s count=%d",
                operation_id,
                len(findings),
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
                    async with httpx.AsyncClient(timeout=5.0) as http:
                        resp = await http.post(
                            f"{opa_url}/v1/data/safecontext/policy/operation_requires_review",
                            json={"input": {"findings": findings_payload}},
                        )
                        if resp.status_code == 200:
                            requires_review = bool(resp.json().get("result", False))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "detector_agent.opa_review_check_failed error=%s", exc
                    )
                    # Conservative: escalate if OPA is unavailable
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
            logger.info("detector_agent.enqueued_sanitize id=%s", operation_id)
        else:
            from workers.agents.reviewer_agent import process_review

            process_review.send(operation_id)
            logger.info("detector_agent.enqueued_review id=%s", operation_id)

    TASKS_TOTAL.labels(agent="detector", status="success").inc()
