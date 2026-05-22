"""Async SQLAlchemy session factory for workers.

Workers are called by Dramatiq in threads that each call asyncio.run(),
creating a NEW event loop per task. We must create the engine INSIDE
each asyncio.run() context to avoid "Future attached to different loop" errors.

Why NOT threading.local for the engine:
  asyncpg binds connections to the asyncio event loop at creation time.
  asyncio.run() creates and closes a new loop per task, so a cached engine
  from the previous call would hold connections bound to a dead loop.
  pool_pre_ping would reconnect, but the engine object itself also holds
  internal loop references that become stale. Creating a fresh engine per
  task is the safe, documented approach for this architecture.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from workers.config import settings


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the current event loop.

    Creates a single-connection engine per call and disposes it on exit.
    This prevents connection leaks when the outbox relay or agents call
    get_session() repeatedly — each call opens exactly 1 connection and
    closes it when the context manager exits.
    """
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=1,        # 1 connection per task — no pool accumulation
        max_overflow=0,     # no extra connections
        pool_recycle=300,   # defensive: engine is short-lived anyway, but this
                            # prevents stale connections if architecture changes
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()  # close connection immediately after use
