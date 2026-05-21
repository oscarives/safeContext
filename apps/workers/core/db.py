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


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the current event loop.

    Creates a single-connection engine per call and disposes it on exit.
    This prevents connection leaks when the outbox relay or agents call
    get_session() repeatedly — each call opens exactly 1 connection and
    closes it when the context manager exits.
    """
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=1,       # 1 connection per task — no pool accumulation
        max_overflow=0,    # no extra connections
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
