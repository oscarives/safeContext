"""Tests for waiver management endpoints — T5.

All DB interactions are mocked — no real infrastructure is required.
Follows the established pattern from test_audit.py.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Environment stubs — must be set BEFORE importing app modules that call
# Settings() at import time.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-for-waivers-hmac-32chars")
os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")

# ---------------------------------------------------------------------------
# App import (after env stubs)
# ---------------------------------------------------------------------------
from httpx import ASGITransport, AsyncClient  # noqa: E402

from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLICY_EDITOR_SUB = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
_VIEWER_SUB = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002"))
_WAIVER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")

_VALID_CREATE_BODY = {
    "rule_id": "SSN_PATTERN",
    "entity_pattern": r"\d{3}-\d{2}-\d{4}",
    "justification": "Approved for internal HR processing pipeline",
}


def _make_mock_waiver(
    *,
    waiver_id: uuid.UUID = _WAIVER_ID,
    rule_id: str = "SSN_PATTERN",
    entity_pattern: str = r"\d{3}-\d{2}-\d{4}",
    justification: str = "Approved for internal HR processing pipeline",
    approved_by: uuid.UUID | None = None,
    status: str = "active",
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    waiver = MagicMock()
    waiver.id = waiver_id
    waiver.rule_id = rule_id
    waiver.entity_pattern = entity_pattern
    waiver.justification = justification
    waiver.approved_by = approved_by or uuid.UUID(_POLICY_EDITOR_SUB)
    waiver.status = status
    waiver.expires_at = expires_at
    waiver.created_at = created_at or datetime(2026, 5, 22, 10, 0, 0, tzinfo=UTC)
    waiver.metadata_ = {}
    return waiver


_SENTINEL = object()  # distinct from None so callers can pass None explicitly


def _make_db_session(*, scalars_result: Any = None, get_result: Any = _SENTINEL) -> AsyncMock:
    """Build a minimal mock AsyncSession."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()

    # .execute() path used by list_waivers
    if scalars_result is not None:
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = scalars_result
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

    # .get() path used by revoke_waiver — always set when a value is provided
    # (including None, which means "record not found")
    if get_result is not _SENTINEL:
        mock_session.get = AsyncMock(return_value=get_result)

    return mock_session


# ---------------------------------------------------------------------------
# Base fixture — authenticated as policy_editor
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def policy_editor_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with policy_editor auth override and basic mock infra."""
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    mock_session = _make_db_session()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    async def _fake_require_auth() -> dict:
        return {
            "sub": _POLICY_EDITOR_SUB,
            "realm_access": {"roles": ["policy_editor"]},
        }

    from core.auth_oidc import require_auth as real_require_auth
    from db import session as session_module
    from db.session import get_db as real_get_db

    with (
        patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
        patch("api.v1.health._check_postgres", return_value="ok"),
        patch("api.v1.health._check_redis", return_value="ok"),
        patch("api.v1.health._check_minio", return_value="ok"),
    ):
        app.dependency_overrides[real_get_db] = _fake_get_db
        app.dependency_overrides[real_require_auth] = _fake_require_auth
        app.state.broker = mock_broker

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with viewer-only role — should be denied write operations."""
    mock_broker = AsyncMock()
    mock_session = _make_db_session()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    async def _fake_require_auth() -> dict:
        return {
            "sub": _VIEWER_SUB,
            "realm_access": {"roles": ["viewer"]},
        }

    from core.auth_oidc import require_auth as real_require_auth
    from db import session as session_module
    from db.session import get_db as real_get_db

    with (
        patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
        patch("api.v1.health._check_postgres", return_value="ok"),
        patch("api.v1.health._check_redis", return_value="ok"),
        patch("api.v1.health._check_minio", return_value="ok"),
    ):
        app.dependency_overrides[real_get_db] = _fake_get_db
        app.dependency_overrides[real_require_auth] = _fake_require_auth
        app.state.broker = mock_broker

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# TestCreateWaiver
# ---------------------------------------------------------------------------


class TestCreateWaiver:
    @pytest.mark.asyncio
    async def test_policy_editor_can_create_waiver(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """POST /v1/waivers with policy_editor role must return 201."""
        mock_waiver = _make_mock_waiver()

        async def _fake_get_db() -> AsyncGenerator[Any, None]:
            session = _make_db_session()
            # After commit+refresh, the endpoint returns the waiver object
            session.refresh = AsyncMock(side_effect=lambda w: None)
            yield session

        from db.models.waiver import Waiver
        from db.session import get_db as real_get_db

        # Patch Waiver constructor to return our controlled mock
        with patch("api.v1.waivers.Waiver") as MockWaiver:
            MockWaiver.return_value = mock_waiver
            app.dependency_overrides[real_get_db] = _fake_get_db

            resp = await policy_editor_client.post("/v1/waivers", json=_VALID_CREATE_BODY)
            app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["rule_id"] == "SSN_PATTERN"
        assert body["status"] == "active"
        assert "id" in body
        assert "approved_by" in body

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_waiver(self, viewer_client: AsyncClient) -> None:
        """POST /v1/waivers with viewer role must return 403."""
        resp = await viewer_client.post("/v1/waivers", json=_VALID_CREATE_BODY)
        assert resp.status_code == 403, resp.text
        assert "policy_editor" in resp.json()["detail"].lower() or "admin" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_waiver_stored_with_correct_approved_by(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """The approved_by field in the response must equal the sub from the JWT."""
        mock_waiver = _make_mock_waiver(approved_by=uuid.UUID(_POLICY_EDITOR_SUB))

        from db.session import get_db as real_get_db

        with patch("api.v1.waivers.Waiver") as MockWaiver:
            MockWaiver.return_value = mock_waiver

            async def _fake_db() -> AsyncGenerator[Any, None]:
                session = _make_db_session()
                session.refresh = AsyncMock(side_effect=lambda w: None)
                yield session

            app.dependency_overrides[real_get_db] = _fake_db
            resp = await policy_editor_client.post("/v1/waivers", json=_VALID_CREATE_BODY)
            app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["approved_by"] == _POLICY_EDITOR_SUB

    @pytest.mark.asyncio
    async def test_create_waiver_with_expiry(self, policy_editor_client: AsyncClient) -> None:
        """POST /v1/waivers with an expires_at date must be accepted."""
        expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        body = {**_VALID_CREATE_BODY, "expires_at": expires_at}

        mock_waiver = _make_mock_waiver(
            expires_at=datetime.fromisoformat(expires_at)
        )

        from db.session import get_db as real_get_db

        with patch("api.v1.waivers.Waiver") as MockWaiver:
            MockWaiver.return_value = mock_waiver

            async def _fake_db() -> AsyncGenerator[Any, None]:
                session = _make_db_session()
                session.refresh = AsyncMock(side_effect=lambda w: None)
                yield session

            app.dependency_overrides[real_get_db] = _fake_db
            resp = await policy_editor_client.post("/v1/waivers", json=body)
            app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 201, resp.text

    @pytest.mark.asyncio
    async def test_create_waiver_missing_rule_id_returns_422(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """POST /v1/waivers without rule_id must return 422 Unprocessable Entity."""
        incomplete = {
            "entity_pattern": r"\d{3}-\d{2}-\d{4}",
            "justification": "Missing rule_id",
        }
        resp = await policy_editor_client.post("/v1/waivers", json=incomplete)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestListWaivers
# ---------------------------------------------------------------------------


class TestListWaivers:
    @pytest.mark.asyncio
    async def test_active_waivers_returned(self, policy_editor_client: AsyncClient) -> None:
        """GET /v1/waivers must return active waivers in the response list."""
        active_waiver = _make_mock_waiver(status="active")

        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(scalars_result=[active_waiver])

        app.dependency_overrides[real_get_db] = _fake_db
        resp = await policy_editor_client.get("/v1/waivers")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["rule_id"] == "SSN_PATTERN"
        assert body[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_empty_list_returned_when_no_active_waivers(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """GET /v1/waivers must return an empty list when no active waivers exist."""
        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(scalars_result=[])

        app.dependency_overrides[real_get_db] = _fake_db
        resp = await policy_editor_client.get("/v1/waivers")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_waivers_requires_auth(self) -> None:
        """GET /v1/waivers without a token must return 401."""
        # Temporarily clear dependency overrides so real auth is enforced
        app.dependency_overrides.clear()

        with (
            patch("api.v1.health._check_postgres", return_value="ok"),
            patch("api.v1.health._check_redis", return_value="ok"),
            patch("api.v1.health._check_minio", return_value="ok"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/v1/waivers")

        # Expect 401 when no token is provided
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_viewer_can_list_waivers(self, viewer_client: AsyncClient) -> None:
        """GET /v1/waivers is accessible to any authenticated role, including viewer."""
        active_waiver = _make_mock_waiver(status="active")

        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(scalars_result=[active_waiver])

        app.dependency_overrides[real_get_db] = _fake_db
        resp = await viewer_client.get("/v1/waivers")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# TestRevokeWaiver
# ---------------------------------------------------------------------------


class TestRevokeWaiver:
    @pytest.mark.asyncio
    async def test_revoke_waiver_returns_204(self, policy_editor_client: AsyncClient) -> None:
        """DELETE /v1/waivers/{id} must return 204 No Content on success."""
        existing_waiver = _make_mock_waiver(status="active")

        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(get_result=existing_waiver)

        app.dependency_overrides[real_get_db] = _fake_db
        resp = await policy_editor_client.delete(f"/v1/waivers/{_WAIVER_ID}")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 204, resp.text

    @pytest.mark.asyncio
    async def test_revoke_waiver_sets_status_revoked(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """DELETE /v1/waivers/{id} must set waiver.status = 'revoked'."""
        existing_waiver = _make_mock_waiver(status="active")

        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(get_result=existing_waiver)

        app.dependency_overrides[real_get_db] = _fake_db
        await policy_editor_client.delete(f"/v1/waivers/{_WAIVER_ID}")
        app.dependency_overrides.pop(real_get_db, None)

        # The endpoint must have mutated the status to 'revoked'
        assert existing_waiver.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_waiver_returns_404(
        self, policy_editor_client: AsyncClient
    ) -> None:
        """DELETE /v1/waivers/{id} with an unknown id must return 404."""
        from db.session import get_db as real_get_db

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(get_result=None)

        app.dependency_overrides[real_get_db] = _fake_db
        resp = await policy_editor_client.delete(f"/v1/waivers/{uuid.uuid4()}")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Waiver not found"

    @pytest.mark.asyncio
    async def test_viewer_cannot_revoke_waiver(self, viewer_client: AsyncClient) -> None:
        """DELETE /v1/waivers/{id} with viewer role must return 403."""
        resp = await viewer_client.delete(f"/v1/waivers/{_WAIVER_ID}")
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_admin_can_revoke_waiver(self) -> None:
        """DELETE /v1/waivers/{id} with admin role must succeed (204)."""
        mock_broker = AsyncMock()
        existing_waiver = _make_mock_waiver(status="active")

        async def _fake_get_db() -> AsyncGenerator[Any, None]:
            yield _make_db_session(get_result=existing_waiver)

        async def _fake_require_auth() -> dict:
            return {
                "sub": str(uuid.uuid4()),
                "realm_access": {"roles": ["admin"]},
            }

        from core.auth_oidc import require_auth as real_require_auth
        from db import session as session_module
        from db.session import get_db as real_get_db

        with (
            patch.object(session_module, "AsyncSessionLocal", return_value=AsyncMock()),
            patch("api.v1.health._check_postgres", return_value="ok"),
            patch("api.v1.health._check_redis", return_value="ok"),
            patch("api.v1.health._check_minio", return_value="ok"),
        ):
            app.dependency_overrides[real_get_db] = _fake_get_db
            app.dependency_overrides[real_require_auth] = _fake_require_auth
            app.state.broker = mock_broker

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.delete(f"/v1/waivers/{_WAIVER_ID}")

            app.dependency_overrides.clear()

        assert resp.status_code == 204, resp.text
