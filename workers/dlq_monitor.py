"""DLQ depth monitor — updates safecontext_dlq_depth Prometheus gauge.

Polls Redis periodically to count messages in the Dramatiq dead-letter queue
(``safecontext_dl``).  Runs as a background asyncio task alongside the worker
process so the gauge is always current without any external cron job.
"""

from __future__ import annotations

import asyncio
import os

import redis.asyncio as aioredis
import structlog

from workers.core.metrics import dlq_depth

log = structlog.get_logger()

# Dramatiq uses the pattern  <queue_name>.DQ  for dead-letter queues when
# using the RedisBroker.  The actual list key in Redis is:
#   dramatiq:<queue_name>.DQ
DLQ_KEY: str = os.environ.get("DLQ_KEY", "dramatiq:safecontext_dl.DQ")
POLL_INTERVAL: int = int(os.environ.get("DLQ_MONITOR_INTERVAL", "15"))


async def monitor_dlq() -> None:
    """Continuously poll Redis for the DLQ depth and update the Prometheus gauge.

    Errors are logged and swallowed so a transient Redis hiccup never brings
    down the worker process.  The gauge simply retains its last value until
    the next successful poll.
    """
    client = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=False,
    )
    log.info(
        "dlq_monitor.started",
        dlq_key=DLQ_KEY,
        poll_interval_s=POLL_INTERVAL,
    )
    while True:
        try:
            depth = await client.llen(DLQ_KEY)
            dlq_depth.set(depth)
            if depth > 0:
                log.warning("dlq.messages_detected", depth=depth, queue=DLQ_KEY)
            else:
                log.debug("dlq.empty", queue=DLQ_KEY)
        except Exception as exc:  # noqa: BLE001
            log.error("dlq_monitor.error", error=str(exc))
        await asyncio.sleep(POLL_INTERVAL)
