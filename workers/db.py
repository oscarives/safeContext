"""Async SQLAlchemy session factory for workers.

Workers are called by Dramatiq in threads that each call asyncio.run(),
creating a NEW event loop per task. We must create the engine INSIDE
each asyncio.run() context to avoid "Future attached to different loop" errors.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _make_session_factory() -> async_sessionmaker:
    """Create a fresh engine + session factory bound to the current event loop."""
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=2,  # small pool — each worker task has its own engine
        max_overflow=5,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the current event loop."""
    factory = _make_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
