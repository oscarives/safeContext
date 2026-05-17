"""Async SQLAlchemy session factory for workers.

Workers use the same DATABASE_URL env var as the API. The engine is created
once per process and shared across tasks.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

_engine = None
_AsyncSessionLocal: async_sessionmaker | None = None


def _get_session_factory() -> async_sessionmaker:
    global _engine, _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        url = os.environ["DATABASE_URL"]
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _AsyncSessionLocal = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession; rolls back on exception, commits otherwise."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
