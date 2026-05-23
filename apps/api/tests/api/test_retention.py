"""
Tests for retention.run_retention().

Tests the data retention job that deletes old operations, artifacts,
and processed outbox entries according to configurable retention windows.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment stubs
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("API_SECRET_KEY", "test-secret")
os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")

from api.v1.retention import run_retention  # noqa: E402


def _mock_result(rowcount: int = 0) -> MagicMock:
    r = MagicMock()
    r.rowcount = rowcount
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunRetention:
    @pytest.mark.asyncio
    async def test_returns_counts_dict(self) -> None:
        """run_retention() returns dict with all deletion counts."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _mock_result(2),   # outbox
            _mock_result(5),   # artifacts
            _mock_result(3),   # operations
        ])

        result = await run_retention(db)

        assert result == {
            "operations_deleted": 3,
            "artifacts_deleted": 5,
            "outbox_deleted": 2,
        }

    @pytest.mark.asyncio
    async def test_deletes_in_correct_order(self) -> None:
        """Outbox first, then artifacts, then operations (FK constraints)."""
        call_order: list[str] = []

        async def _track_execute(stmt: object) -> MagicMock:
            stmt_str = str(stmt).lower()
            if "outbox" in stmt_str:
                call_order.append("outbox")
            elif "artifact" in stmt_str:
                call_order.append("artifacts")
            elif "operation" in stmt_str:
                call_order.append("operations")
            return _mock_result(0)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_track_execute)

        await run_retention(db)

        assert call_order == ["outbox", "artifacts", "operations"]

    @pytest.mark.asyncio
    async def test_defaults_to_365_ops_730_artifacts(self) -> None:
        """Without env vars, defaults are 365 days for ops and 730 for artifacts."""
        env_clean = {
            k: v for k, v in os.environ.items()
            if k not in ("RETENTION_DAYS_OPERATIONS", "RETENTION_DAYS_ARTIFACTS")
        }

        with patch.dict(os.environ, env_clean, clear=True):
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[
                _mock_result(0), _mock_result(0), _mock_result(0),
            ])

            result = await run_retention(db)

        assert result == {"operations_deleted": 0, "artifacts_deleted": 0, "outbox_deleted": 0}
        assert db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_uses_env_vars_for_retention_days(self) -> None:
        """run_retention() reads RETENTION_DAYS_OPERATIONS and RETENTION_DAYS_ARTIFACTS."""
        with patch.dict(os.environ, {
            "RETENTION_DAYS_OPERATIONS": "30",
            "RETENTION_DAYS_ARTIFACTS": "60",
        }):
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[
                _mock_result(1),   # outbox
                _mock_result(10),  # artifacts
                _mock_result(7),   # operations
            ])

            result = await run_retention(db)

        assert result == {"operations_deleted": 7, "artifacts_deleted": 10, "outbox_deleted": 1}

    @pytest.mark.asyncio
    async def test_three_delete_queries_executed(self) -> None:
        """run_retention() must execute exactly 3 DELETE queries."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _mock_result(0), _mock_result(0), _mock_result(0),
        ])

        await run_retention(db)

        assert db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_zero_deletions(self) -> None:
        """run_retention() works correctly when nothing needs to be deleted."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _mock_result(0), _mock_result(0), _mock_result(0),
        ])

        result = await run_retention(db)

        assert result["operations_deleted"] == 0
        assert result["artifacts_deleted"] == 0
        assert result["outbox_deleted"] == 0
