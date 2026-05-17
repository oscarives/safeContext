"""RedisBrokerAdapter — BrokerPort backed by Redis lists.

ADR-011: This is the ONLY module in workers/ that imports redis.
Queues follow the naming convention  safecontext:<queue_name>.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from workers.core.ports import BrokerPort

logger = logging.getLogger(__name__)


class RedisBrokerAdapter(BrokerPort):
    """BrokerPort implementation using Redis rpush / blpop.

    ADR-002: Redis is ephemeral; it is never the source of truth.
    The outbox in PostgreSQL is the authoritative queue source.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: aioredis.Redis | None = None  # type: ignore[type-arg]

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._client.ping()
        logger.info("redis_broker.connected url=%s", self._url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("redis_broker.disconnected")

    # ── BrokerPort ───────────────────────────────────────────────────────────

    async def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        if self._client is None:
            raise RuntimeError(
                "RedisBrokerAdapter not connected — call connect() first"
            )
        redis_key = f"safecontext:{queue}"
        payload = json.dumps(message)
        await self._client.rpush(redis_key, payload)
        logger.debug("redis_broker.enqueued queue=%s", redis_key)
