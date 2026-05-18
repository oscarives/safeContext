"""workers/main.py — entrypoint for the SafeContext worker process.

This module:
  1. Configures the Dramatiq broker (RedisBroker).
  2. Configures the Dead-Letter Queue middleware.
  3. Imports all actor modules so Dramatiq discovers them.
  4. Optionally starts the Prometheus metrics server.
  5. Optionally starts the outbox relay loop in a background thread.
  6. Starts OPA hot-reload polling and DLQ depth monitoring as asyncio tasks.
  7. Installs SIGTERM/SIGINT handlers for graceful shutdown.

Usage:
    python -m dramatiq workers.agents --processes 2 --threads 4

Or via the Docker CMD defined in workers/Dockerfile.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import threading

import dramatiq
import structlog
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AgeLimit, Retries, TimeLimit

logger = logging.getLogger(__name__)
log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Broker + Middleware configuration
# ---------------------------------------------------------------------------

_redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

broker = RedisBroker(
    url=_redis_url,
    # Dead-Letter Queue — messages that exceed max_retries go to safecontext_dl
    middleware=[
        AgeLimit(),
        TimeLimit(),
        Retries(
            max_retries=3,
            min_backoff=1_000,
            max_backoff=30_000,
        ),
    ],
)

# Configure DLQ: failed messages (after 3 retries) land in safecontext_dl
# Dramatiq's RedisBroker uses a dead-letter queue suffix by default.
# We override the dead_message_ttl to keep DLQ messages for 7 days.
broker.dead_message_ttl = 7 * 24 * 60 * 60 * 1_000  # 7 days in ms

dramatiq.set_broker(broker)

# ---------------------------------------------------------------------------
# Import all actor modules — Dramatiq actor discovery
# ---------------------------------------------------------------------------

import workers.agents.detector_agent  # noqa: F401
import workers.agents.sanitizer_agent  # noqa: F401
import workers.agents.classifier_agent  # noqa: F401
import workers.agents.auditor_agent  # noqa: F401
import workers.agents.reviewer_agent  # noqa: F401

# ---------------------------------------------------------------------------
# Prometheus metrics HTTP server (optional)
# ---------------------------------------------------------------------------


def _start_metrics_server() -> None:
    """Start Prometheus metrics server on METRICS_PORT (default 9090)."""
    port: int = int(os.environ.get("METRICS_PORT", "9090"))
    try:
        from prometheus_client import start_http_server
        start_http_server(port)
        logger.info("metrics_server.started port=%d", port)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_server.failed error=%s", exc)


# ---------------------------------------------------------------------------
# Outbox relay (optional background thread)
# ---------------------------------------------------------------------------


def _start_outbox_relay() -> None:
    """Start the outbox relay loop in a daemon thread."""
    import asyncio

    def _run() -> None:
        from workers.outbox_relay import run_relay_loop
        asyncio.run(run_relay_loop())

    thread = threading.Thread(target=_run, daemon=True, name="outbox-relay")
    thread.start()
    logger.info("outbox_relay.thread_started")


# ---------------------------------------------------------------------------
# Module-level startup when run directly or via Dramatiq CLI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Graceful shutdown — SIGTERM / SIGINT
# ---------------------------------------------------------------------------


def _handle_sigterm(*_: object) -> None:
    """Graceful shutdown: let Dramatiq drain current tasks, then exit.

    Dramatiq's RedisBroker already flushes in-progress messages on SIGTERM.
    This handler stops our background tasks cleanly before the process exits.
    """
    log.info("worker.sigterm_received", action="finishing_current_tasks")
    # Signal background tasks to stop (best-effort; process exits shortly)
    try:
        from workers.core.opa_client import opa_client
        # Schedule stop in the background event loop if one is running
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(opa_client.stop()))
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


# ---------------------------------------------------------------------------
# Background asyncio tasks: OPA hot-reload + DLQ monitor
# ---------------------------------------------------------------------------


async def _startup_background_tasks() -> None:
    """Launch OPA polling, DLQ monitoring and recall evaluation as background tasks."""
    from workers.core.opa_client import opa_client
    from workers.dlq_monitor import monitor_dlq
    from workers.ml.recall_evaluator import run_recall_loop

    asyncio.create_task(opa_client.start_polling(), name="opa-hot-reload")
    asyncio.create_task(monitor_dlq(), name="dlq-monitor")
    asyncio.create_task(run_recall_loop(), name="recall-evaluator")
    log.info("worker.background_tasks_started")


def _start_background_tasks() -> None:
    """Run the async startup in a dedicated daemon thread with its own event loop."""
    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_startup_background_tasks())
        loop.run_forever()  # keep the loop alive so the tasks continue running

    thread = threading.Thread(
        target=_run, daemon=True, name="background-tasks"
    )
    thread.start()
    logger.info("background_tasks.thread_started")


# ---------------------------------------------------------------------------
# Module-level startup when run directly or via Dramatiq CLI
# ---------------------------------------------------------------------------

if os.environ.get("START_METRICS_SERVER", "true").lower() == "true":
    _start_metrics_server()

if os.environ.get("START_OUTBOX_RELAY", "true").lower() == "true":
    _start_outbox_relay()

if os.environ.get("START_BACKGROUND_TASKS", "true").lower() == "true":
    _start_background_tasks()

logger.info(
    "workers.main.ready redis_url=%s",
    _redis_url.replace(
        _redis_url.split("@")[-1] if "@" in _redis_url else "", "***"
    ),
)
