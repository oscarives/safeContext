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
import json
import logging
import os

import structlog
from sqlalchemy import select, update

from workers.db import get_session
from workers.adapters.redis_broker import RedisBrokerAdapter
from workers.core.metrics import OUTBOX_EVENTS_RELAYED, OUTBOX_RELAY_ERRORS, OUTBOX_LAG_EVENTS

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
    "document.scan_requested": "safecontext_scan",
    "document.sanitize_requested": "safecontext_sanitize",
    "document.classify_requested": "safecontext_classify",
    "document.audit_requested": "safecontext_audit",
    "document.review_requested": "safecontext_review",
}

_POLL_INTERVAL_SECONDS: float = float(
    os.environ.get("OUTBOX_POLL_INTERVAL", "1.0")
)
_BATCH_SIZE: int = int(os.environ.get("OUTBOX_BATCH_SIZE", "10"))


async def relay_once(broker: RedisBrokerAdapter) -> int:
    """Process one batch of unprocessed outbox events.

    Returns the number of events relayed in this batch.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
    from db.models.outbox import Outbox

    relayed = 0

    async with get_session() as session:
        result = await session.execute(
            select(Outbox)
            .where(Outbox.processed == False)  # noqa: E712
            .order_by(Outbox.created_at)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()

        OUTBOX_LAG_EVENTS.set(len(events))

        for event in events:
            queue_name = _EVENT_TO_QUEUE.get(event.event_type)
            if queue_name is None:
                logger.warning(
                    "outbox_relay.unknown_event_type",
                    event_type=event.event_type,
                    outbox_id=str(event.id),
                )
                # Mark as processed to avoid infinite retry on unknown types
                await session.execute(
                    update(Outbox)
                    .where(Outbox.id == event.id)
                    .values(processed=True)
                )
                continue

            operation_id: str = event.payload.get("operation_id", "")

            # Dramatiq envelope format
            dramatiq_message = {
                "queue_name": queue_name,
                "actor_name": _queue_to_actor(queue_name),
                "args": [operation_id],
                "kwargs": {},
                "options": {},
                "message_id": str(event.id),
                "message_timestamp": int(event.created_at.timestamp() * 1000),
            }

            try:
                await broker.enqueue(queue_name, dramatiq_message)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "outbox_relay.enqueue_failed",
                    outbox_id=str(event.id),
                    queue=queue_name,
                    error=str(exc),
                )
                OUTBOX_RELAY_ERRORS.inc()
                raise  # re-raise to roll back session — event stays unprocessed

            # Mark processed AFTER successful enqueue
            await session.execute(
                update(Outbox)
                .where(Outbox.id == event.id)
                .values(processed=True)
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


def _queue_to_actor(queue_name: str) -> str:
    return {
        "safecontext_scan": "process_scan",
        "safecontext_sanitize": "process_sanitize",
        "safecontext_classify": "process_classify",
        "safecontext_audit": "process_audit",
        "safecontext_review": "process_review",
    }.get(queue_name, "unknown")


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
