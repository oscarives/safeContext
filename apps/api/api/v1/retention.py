"""Retention job — deletes operations and related data older than retention_days.

Configurable via env:
  RETENTION_DAYS_OPERATIONS=365   (default)
  RETENTION_DAYS_ARTIFACTS=730    (default)

Usage (from a scheduler, cron, or management command):

    from db.session import AsyncSessionLocal
    from api.v1.retention import run_retention

    async with AsyncSessionLocal() as db:
        stats = await run_retention(db)
        print(stats)  # {"operations_deleted": N, "artifacts_deleted": M}

Operations are deleted after their related artifacts because artifacts have
a FK to operations (ON DELETE CASCADE), but we handle artifacts explicitly
first to allow independent artifact retention windows.
"""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.artifact import Artifact
from db.models.operation import Operation

logger = get_logger(__name__)


async def run_retention(db: AsyncSession) -> dict[str, int]:
    """Delete stale operations and artifacts according to configured retention windows.

    Returns a dict with the counts of deleted rows for each table.
    Both deletes run inside a single transaction; if either fails the
    transaction is rolled back (the caller is responsible for committing).
    """
    ops_days = int(os.environ.get("RETENTION_DAYS_OPERATIONS", 365))
    art_days = int(os.environ.get("RETENTION_DAYS_ARTIFACTS", 730))

    cutoff_ops = datetime.now(UTC) - timedelta(days=ops_days)
    cutoff_art = datetime.now(UTC) - timedelta(days=art_days)

    logger.info(
        "retention.run.start",
        ops_days=ops_days,
        art_days=art_days,
        cutoff_ops=cutoff_ops.isoformat(),
        cutoff_art=cutoff_art.isoformat(),
    )

    # Delete orphaned / old artifacts first so that the FK constraint
    # (artifacts.operation_id → operations.id) does not block operation deletes
    # for artifacts whose operation was already removed in a prior run.
    art_result = await db.execute(delete(Artifact).where(Artifact.created_at < cutoff_art))
    n_art: int = art_result.rowcount  # type: ignore[assignment]

    # Delete operations; ON DELETE CASCADE removes remaining child rows
    # (findings, redactions, artifacts created after the artifact cutoff).
    ops_result = await db.execute(delete(Operation).where(Operation.created_at < cutoff_ops))
    n_ops: int = ops_result.rowcount  # type: ignore[assignment]

    logger.info(
        "retention.run.complete",
        operations_deleted=n_ops,
        artifacts_deleted=n_art,
    )

    return {"operations_deleted": n_ops, "artifacts_deleted": n_art}
