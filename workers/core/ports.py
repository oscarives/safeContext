"""ADR-011: Port/Adapter interfaces for workers.

These abstract base classes define the boundaries between the worker domain
logic and infrastructure concerns (broker, storage, cache). No infrastructure
import is allowed here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrokerPort(ABC):
    """Abstraction over message queues (Redis, etc.)."""

    @abstractmethod
    async def enqueue(self, queue: str, message: dict[str, Any]) -> None:
        """Push *message* onto *queue*."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the broker."""
        ...


class StoragePort(ABC):
    """Abstraction over object storage (MinIO / S3)."""

    @abstractmethod
    async def put(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Store *data* under *key*.

        Returns the SHA-256 hex digest of the stored object.
        """
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve bytes stored under *key*."""
        ...


class CachePort(ABC):
    """Abstraction over ephemeral key-value store (Redis)."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the value for *key*, or None if absent / expired."""
        ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """Store *value* under *key* with *ttl* seconds expiry."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove *key* from the cache."""
        ...
