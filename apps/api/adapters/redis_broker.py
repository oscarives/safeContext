import json
from typing import Any

import redis.asyncio as aioredis

from core.logging import get_logger
from core.ports import BrokerPort

logger = get_logger(__name__)


class RedisBrokerAdapter(BrokerPort):
    """BrokerPort implementation backed by Redis lists (rpush / blpop).

    This is the ONLY module in the API that imports redis.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: aioredis.Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        # Verify connectivity
        await self._client.ping()
        logger.info("redis_broker.connected", url=self._url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("redis_broker.disconnected")

    async def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        if self._client is None:
            raise RuntimeError("RedisBrokerAdapter not connected — call connect() first")
        payload = json.dumps(message)
        await self._client.rpush(queue, payload)
        logger.debug("redis_broker.enqueued", queue=queue)

    async def enqueue_batch(self, queue: str, messages: list[dict[str, Any]]) -> None:
        """Enqueue multiple messages atomically using a Redis pipeline.

        All messages are pushed to the queue in a single round-trip,
        reducing latency proportional to the batch size.
        """
        if self._client is None:
            raise RuntimeError("RedisBrokerAdapter not connected — call connect() first")
        if not messages:
            return
        async with self._client.pipeline(transaction=True) as pipe:
            for msg in messages:
                pipe.rpush(queue, json.dumps(msg))
            await pipe.execute()
        logger.debug("redis_broker.enqueued_batch", queue=queue, count=len(messages))
