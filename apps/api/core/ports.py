from abc import ABC, abstractmethod
from typing import Any


class BrokerPort(ABC):
    @abstractmethod
    async def enqueue(self, queue: str, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def enqueue_batch(self, queue: str, messages: list[dict[str, Any]]) -> None:
        """Enqueue multiple messages atomically using a pipeline.

        Default implementation falls back to sequential enqueue calls.
        Subclasses should override for efficient batch operations.
        """
        for msg in messages:
            await self.enqueue(queue, msg)

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
