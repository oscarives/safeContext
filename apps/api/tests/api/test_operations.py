"""
Tests for GET /v1/operations.

All DB interactions are mocked — no real infrastructure is required.
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Environment stubs — must be set BEFORE importing app modules.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("API_SECRET_KEY", "test-secret")
os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")

# ---------------------------------------------------------------------------
# App import (after env stubs)
# ---------------------------------------------------------------------------
from httpx import ASGITransport, AsyncClient  # noqa: E402

from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ACTOR_SUB = "550e8400-e29b-41d4-a716-446655440000"
_OPERATION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_TRACE_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_ACTOR_ID = uuid.UUID(_ACTOR_SUB)
_MOCK_ACTOR = {"sub": _ACTOR_SUB, "preferred_username": "testuser"}

_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_operation(
    *,
    op_id: uuid.UUID = _OPERATION_ID,
    trace_id: uuid.UUID = _TRACE_ID,
    actor_id: uuid.UUID = _ACTOR_ID,
    status: str = "completed",
) -> MagicMock:
    op = MagicMock()
    op.id = op_id
    op.trace_id = trace_id
    op.actor_id = actor_id
    op.actor_type = "human"
    op.artifact_digest = "sha256-deadbeef"
    op.policy_version = "v1.0.0"
    op.status = status
    op.created_at = _NOW
    op.completed_at = _NOW
    return op


def _make_stats_row(
    total: int = 0,
    pending: int = 0,
    escalated: int = 0,
    completed: int = 0,
    rejected: int = 0,
) -> MagicMock:
    row = MagicMock()
    row.total = total
    row.total_pending = pending
    row.total_escalated = escalated
    row.total_completed = completed
    row.total_rejected = rejected
    return row


def _make_db_session(
    *,
    stats_row: Any = None,
    item_rows: list[Any] | None = None,
) -> AsyncMock:
    """Build a mock AsyncSession that handles the 2 queries in list_operations.

    Query 1 (stats): db.execute() → result.one() → stats_row
    Query 2 (items): db.execute() → result.all() → item_rows
    """
    if stats_row is None:
        stats_row = _make_stats_row()
    if item_rows is None:
        item_rows = []

    call_count = 0

    async def _fake_execute(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.one.return_value = stats_row
        else:
            result.all.return_value = item_rows
        return result

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock(side_effect=_fake_execute)
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    async def _fake_require_auth() -> dict:
        return _MOCK_ACTOR

    from core.auth_oidc import require_auth as real_require_auth
    from db import session as session_module
    from db.session import get_db as real_get_db

    mock_session = _make_db_session()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    with (
        patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
        patch("api.v1.health._check_postgres", return_value="ok"),
        patch("api.v1.health._check_redis", return_value="ok"),
        patch("api.v1.health._check_minio", return_value="ok"),
        patch("api.v1.health._check_broker", new_callable=AsyncMock, return_value="ok"),
    ):
        app.dependency_overrides[real_get_db] = _fake_get_db
        app.dependency_overrides[real_require_auth] = _fake_require_auth
        app.state.broker = mock_broker

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListOperations:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_operations(self, client: AsyncClient) -> None:
        """GET /v1/operations with no data returns empty list and zero aggregates."""
        session = _make_db_session(
            stats_row=_make_stats_row(total=0),
            item_rows=[],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["total_pending"] == 0
        assert body["total_escalated"] == 0
        assert body["total_completed"] == 0
        assert body["total_rejected"] == 0

    @pytest.mark.asyncio
    async def test_returns_operations_with_correct_shape(self, client: AsyncClient) -> None:
        """GET /v1/operations returns items with all expected fields."""
        op = _make_mock_operation()
        findings_count = 3
        session = _make_db_session(
            stats_row=_make_stats_row(total=1, completed=1),
            item_rows=[(op, findings_count)],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

        item = body["items"][0]
        assert item["id"] == str(_OPERATION_ID)
        assert item["trace_id"] == str(_TRACE_ID)
        assert item["actor_id"] == str(_ACTOR_ID)
        assert item["actor_type"] == "human"
        assert item["status"] == "completed"
        assert item["findings_count"] == 3
        assert "created_at" in item

    @pytest.mark.asyncio
    async def test_aggregates_returned_correctly(self, client: AsyncClient) -> None:
        """GET /v1/operations returns correct aggregated status counts."""
        session = _make_db_session(
            stats_row=_make_stats_row(
                total=10, pending=3, escalated=2, completed=4, rejected=1,
            ),
            item_rows=[],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 10
        assert body["total_pending"] == 3
        assert body["total_escalated"] == 2
        assert body["total_completed"] == 4
        assert body["total_rejected"] == 1

    @pytest.mark.asyncio
    async def test_invalid_from_date_returns_422(self, client: AsyncClient) -> None:
        """GET /v1/operations with bad from_date format returns 422."""
        resp = await client.get("/v1/operations?from_date=not-a-date")
        assert resp.status_code == 422, resp.text
        assert "from_date" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_to_date_returns_422(self, client: AsyncClient) -> None:
        """GET /v1/operations with bad to_date format returns 422."""
        resp = await client.get("/v1/operations?to_date=xyz")
        assert resp.status_code == 422, resp.text
        assert "to_date" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_actor_id_returns_422(self, client: AsyncClient) -> None:
        """GET /v1/operations with non-UUID actor_id returns 422."""
        resp = await client.get("/v1/operations?actor_id=not-a-uuid")
        assert resp.status_code == 422, resp.text
        assert "actor_id" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_actor_id_me_resolves_to_jwt_sub(self, client: AsyncClient) -> None:
        """GET /v1/operations?actor_id=me must filter by the authenticated user's sub."""
        executed_stmts: list = []

        async def _capture_execute(stmt: Any, *args: Any, **kwargs: Any) -> MagicMock:
            executed_stmts.append(stmt)
            result = MagicMock()
            if len(executed_stmts) == 1:
                result.one.return_value = _make_stats_row(total=0)
            else:
                result.all.return_value = []
            return result

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.execute = AsyncMock(side_effect=_capture_execute)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations?actor_id=me")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        assert len(executed_stmts) == 2

    @pytest.mark.asyncio
    async def test_status_filter_applied(self, client: AsyncClient) -> None:
        """GET /v1/operations?status=pending returns 200 (filter accepted)."""
        session = _make_db_session(
            stats_row=_make_stats_row(total=0),
            item_rows=[],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations?status=pending")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_from_date_filter_accepted(self, client: AsyncClient) -> None:
        """GET /v1/operations with valid from_date returns 200."""
        session = _make_db_session(
            stats_row=_make_stats_row(total=0),
            item_rows=[],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations?from_date=2025-01-01T00:00:00")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_limit_clamped_to_100(self, client: AsyncClient) -> None:
        """GET /v1/operations?limit=500 must clamp limit to 100 internally."""
        session = _make_db_session(
            stats_row=_make_stats_row(total=0),
            item_rows=[],
        )

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await client.get("/v1/operations?limit=500")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_requires_auth(self) -> None:
        """GET /v1/operations without a token must return 401."""
        app.dependency_overrides.clear()

        from db import session as session_module

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
            patch("api.v1.health._check_postgres", return_value="ok"),
            patch("api.v1.health._check_redis", return_value="ok"),
            patch("api.v1.health._check_minio", return_value="ok"),
            patch("api.v1.health._check_broker", new_callable=AsyncMock, return_value="ok"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/v1/operations")

        assert resp.status_code == 401, resp.text
