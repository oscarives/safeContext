"""outbox_relay — polls PostgreSQL outbox and enqueues events into Redis.

ADR-002 / ADR-007: Redis is ephemeral and NEVER the source of truth.
The outbox table in PostgreSQL is the authoritative event queue. This relay
reads unprocessed events, enqueues them in Redis (for Dramatiq actors), then
marks them as processed in PG — in that order.

Transactional guarantee:
  - If Redis enqueue fails, the PG row stays unprocessed → will be retried.
  - If PG update fails after Redis enqueue, the event may be delivered twice
    but each actor has idempotency guards to handle this safely.

Run this as a single-process service alongside the Dramatiq workers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import structlog
from sqlalchemy import func, select, update

# Resolve the API package path once at module load — not on every relay call.
# Both this module and all agents reach into apps/api for the shared DB models.
# Long-term fix: extract models into a shared safecontext-db package.
_api_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api")
)
if _api_path not in sys.path:
    sys.path.insert(0, _api_path)

from db.models.outbox import Outbox  # noqa: E402 (must follow sys.path setup)

from workers.core.db import get_session
from workers.adapters.redis_broker import RedisBrokerAdapter
from workers.core.metrics import (
    OUTBOX_EVENTS_RELAYED,
    OUTBOX_RELAY_ERRORS,
    OUTBOX_LAG_EVENTS,
)

# Bootstrap structlog for structured JSON output
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Event type → Dramatiq queue name mapping
_EVENT_TO_QUEUE: dict[str, str] = {
    # API writes these event types (without "document." prefix)
    "scan_requested": "safecontext_scan",
    "sanitize_requested": "safecontext_sanitize",
    "classify_requested": "safecontext_classify",
    "audit_requested": "safecontext_audit",
    "review_requested": "safecontext_review",
    # legacy prefixed variants
    "document.scan_requested": "safecontext_scan",
    "document.sanitize_requested": "safecontext_sanitize",
    "document.classify_requested": "safecontext_classify",
}

_POLL_INTERVAL_SECONDS: float = float(os.environ.get("OUTBOX_POLL_INTERVAL", "1.0"))
_BATCH_SIZE: int = int(os.environ.get("OUTBOX_BATCH_SIZE", "10"))


async def relay_once(broker: RedisBrokerAdapter) -> int:
    """Process one batch of unprocessed outbox events.

    Returns the number of events relayed in this batch.
    """
    relayed = 0

    async with get_session() as session:
        # Report true backlog, not just the current batch size.
        total_lag = (await session.execute(
            select(func.count()).select_from(Outbox).where(Outbox.processed == False)  # noqa: E712
        )).scalar_one()
        OUTBOX_LAG_EVENTS.set(total_lag)

        result = await session.execute(
            select(Outbox)
            .where(Outbox.processed == False)  # noqa: E712
            .order_by(Outbox.created_at)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()

        for event in events:
            queue_name = _EVENT_TO_QUEUE.get(event.event_type)
            if queue_name is None:
                logger.error(
                    "outbox_relay.unknown_event_type",
                    event_type=event.event_type,
                    outbox_id=str(event.id),
                )
                # Do NOT mark as processed — leave for operator inspection.
                # The OUTBOX_LAG_EVENTS gauge and an alert on stale unprocessed rows
                # will surface this. Silently discarding breaks the audit trail.
                OUTBOX_RELAY_ERRORS.inc()
                continue

            operation_id: str = event.payload.get("operation_id", "")

            try:
                actor = _get_actor(queue_name)
                if actor is None:
                    logger.error(
                        "outbox_relay.no_actor_for_queue",
                        queue=queue_name,
                        outbox_id=str(event.id),
                    )
                    # Do NOT mark as processed — configuration error, needs operator fix.
                    OUTBOX_RELAY_ERRORS.inc()
                    continue
                actor.send(operation_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "outbox_relay.enqueue_failed",
                    outbox_id=str(event.id),
                    queue=queue_name,
                    error=str(exc),
                )
                OUTBOX_RELAY_ERRORS.inc()
                raise

            # Mark processed AFTER successful enqueue
            await session.execute(
                update(Outbox).where(Outbox.id == event.id).values(processed=True)
            )

            OUTBOX_EVENTS_RELAYED.labels(event_type=event.event_type).inc()
            relayed += 1
            logger.info(
                "outbox_relay.relayed",
                outbox_id=str(event.id),
                event_type=event.event_type,
                queue=queue_name,
                operation_id=operation_id,
            )

    return relayed


def _get_actor(queue_name: str):  # type: ignore[return]
    """Return the Dramatiq actor for a given queue name."""
    from workers.agents.detector_agent import process_scan
    from workers.agents.sanitizer_agent import process_sanitize
    from workers.agents.classifier_agent import process_classify
    from workers.agents.auditor_agent import process_audit
    from workers.agents.reviewer_agent import process_review

    return {
        "safecontext_scan": process_scan,
        "safecontext_sanitize": process_sanitize,
        "safecontext_classify": process_classify,
        "safecontext_audit": process_audit,
        "safecontext_review": process_review,
    }.get(queue_name)


async def run_relay_loop() -> None:
    """Main relay loop: poll → relay → sleep, forever."""
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    broker = RedisBrokerAdapter(url=redis_url)

    logger.info("outbox_relay.starting", redis_url=redis_url)
    await broker.connect()

    try:
        while True:
            try:
                relayed = await relay_once(broker)
                if relayed > 0:
                    logger.debug("outbox_relay.batch_done", relayed=relayed)
            except Exception as exc:  # noqa: BLE001
                logger.error("outbox_relay.loop_error", error=str(exc))
                OUTBOX_RELAY_ERRORS.inc()

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        await broker.disconnect()
        logger.info("outbox_relay.stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_relay_loop())
