"""
Tests for POST /v1/scan and GET /health.

All DB and broker interactions are mocked so no real infrastructure is needed.
"""

# ---------------------------------------------------------------------------
# Environment stubs — must be set BEFORE importing app modules that call
# Settings() at import time.
# ---------------------------------------------------------------------------
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("API_SECRET_KEY", "test-secret")
os.environ["MCP_AUTH_TOKEN"] = "test-token"  # must match header below

# ---------------------------------------------------------------------------
# App import (after env stubs)
# ---------------------------------------------------------------------------
from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an AsyncClient wired to the FastAPI app.

    We bypass the real lifespan (no Redis/PG/OTel) and inject a mock broker
    directly into app.state so scan.py can call broker.enqueue().
    """
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    # Patch DB session so no real Postgres connection is attempted
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    from db import session as session_module

    with (
        patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
        patch(
            "api.v1.scan.get_db",
            return_value=_fake_get_db(),
        ),
        patch("api.v1.health._check_postgres", return_value="ok"),
        patch("api.v1.health._check_redis", return_value="ok"),
        patch("api.v1.health._check_minio", return_value="ok"),
    ):
        # Override the FastAPI dependency for get_db
        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _fake_get_db
        app.state.broker = mock_broker
        # Sync settings token with test header value
        from config import settings as _settings

        _settings.mcp_auth_token = "test-token"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer test-token"},
        ) as ac:
            yield ac

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /v1/scan tests
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "document": "Hello, my name is John Doe and my SSN is 123-45-6789.",
    "policy_name": "pii-standard",
}


@pytest.mark.asyncio
async def test_scan_returns_trace_id(client: AsyncClient) -> None:
    """POST /v1/scan with valid body must return a valid UUID trace_id."""
    resp = await client.post("/v1/scan", json=_VALID_PAYLOAD)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "trace_id" in body
    # Must be a parseable UUID
    trace_id = uuid.UUID(body["trace_id"])
    assert isinstance(trace_id, uuid.UUID)


@pytest.mark.asyncio
async def test_scan_header_has_trace_id(client: AsyncClient) -> None:
    """POST /v1/scan response must include X-Trace-ID header matching body trace_id."""
    resp = await client.post("/v1/scan", json=_VALID_PAYLOAD)
    assert resp.status_code == 200, resp.text
    assert "x-trace-id" in resp.headers
    header_trace_id = resp.headers["x-trace-id"]
    body_trace_id = resp.json()["trace_id"]
    assert header_trace_id == body_trace_id


@pytest.mark.asyncio
async def test_scan_requires_document_field(client: AsyncClient) -> None:
    """POST /v1/scan without 'document' field must return HTTP 422."""
    resp = await client.post("/v1/scan", json={"policy_name": "pii-standard"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_scan_requires_policy_name(client: AsyncClient) -> None:
    """POST /v1/scan without 'policy_name' field must return HTTP 422."""
    resp = await client.post(
        "/v1/scan",
        json={"document": "Some text without policy."},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /health tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    """GET /health must return HTTP 200 with expected structure."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "postgres" in body
    assert "redis" in body
    assert "minio" in body
