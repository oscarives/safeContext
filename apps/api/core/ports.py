from abc import ABC, abstractmethod
from typing import Any


class BrokerPort(ABC):
    @abstractmethod
    async def enqueue(self, queue: str, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
