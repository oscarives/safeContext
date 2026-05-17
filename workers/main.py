"""workers/main.py — entrypoint for the SafeContext worker process.

This module:
  1. Configures the Dramatiq broker (RedisBroker).
  2. Configures the Dead-Letter Queue middleware.
  3. Imports all actor modules so Dramatiq discovers them.
  4. Optionally starts the Prometheus metrics server.
  5. Optionally starts the outbox relay loop in a background thread.

Usage:
    python -m dramatiq workers.agents --processes 2 --threads 4

Or via the Docker CMD defined in workers/Dockerfile.
"""
from __future__ import annotations

import logging
import os
import threading

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AgeLimit, Retries, TimeLimit

logger = logging.getLogger(__name__)

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

if os.environ.get("START_METRICS_SERVER", "true").lower() == "true":
    _start_metrics_server()

if os.environ.get("START_OUTBOX_RELAY", "true").lower() == "true":
    _start_outbox_relay()

logger.info(
    "workers.main.ready redis_url=%s",
    _redis_url.replace(
        _redis_url.split("@")[-1] if "@" in _redis_url else "", "***"
    ),
)
