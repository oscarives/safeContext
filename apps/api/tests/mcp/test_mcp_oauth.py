"""Tests T8 — OAuth 2.1 JWT validation for MCP endpoints.

Covers:
- Missing Authorization header → 401
- Invalid / random token in production mode → 401
- Valid JWT with correct audience → payload returned
- Valid JWT with wrong audience → 401
- Dev mode static token → 200 (backward compat)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from main import app  # import at module level — same pattern as other MCP test files
from mcp.auth import require_mcp_oauth


# ── Unit tests for require_mcp_oauth ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_missing_auth_returns_401():
    """No Authorization header → 401."""
    with pytest.raises(HTTPException) as exc_info:
        await require_mcp_oauth(credentials=None)
    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_mcp_invalid_token_returns_401():
    """Random token in production mode → 401 (JWT decode fails)."""
    from config import settings

    original_env = settings.safecontext_env
    settings.safecontext_env = "production"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-real-jwt")

        with patch("mcp.auth._decode_token", new_callable=AsyncMock) as mock_decode:
            mock_decode.side_effect = Exception("invalid signature")
            with pytest.raises(HTTPException) as exc_info:
                await require_mcp_oauth(credentials=creds)
        assert exc_info.value.status_code == 401
        assert "Invalid MCP token" in exc_info.value.detail
    finally:
        settings.safecontext_env = original_env


@pytest.mark.asyncio
async def test_mcp_valid_jwt_with_correct_audience():
    """Valid JWT with audience='safecontext-api' → payload returned."""
    from config import settings

    original_env = settings.safecontext_env
    settings.safecontext_env = "production"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        fake_payload = {
            "sub": "agent-abc",
            "aud": ["safecontext-api"],
            "scope": "mcp:scan mcp:sanitize",
        }
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")

        with patch("mcp.auth._decode_token", new_callable=AsyncMock) as mock_decode:
            mock_decode.return_value = fake_payload
            result = await require_mcp_oauth(credentials=creds)

        assert result["sub"] == "agent-abc"
        assert result["scope"] == "mcp:scan mcp:sanitize"
    finally:
        settings.safecontext_env = original_env


@pytest.mark.asyncio
async def test_mcp_jwt_wrong_audience_returns_401():
    """Valid JWT but audience does not include 'safecontext-api' → 401."""
    from config import settings

    original_env = settings.safecontext_env
    settings.safecontext_env = "production"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        fake_payload = {
            "sub": "agent-abc",
            "aud": ["some-other-service"],
            "scope": "mcp:scan",
        }
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")

        with patch("mcp.auth._decode_token", new_callable=AsyncMock) as mock_decode:
            mock_decode.return_value = fake_payload
            with pytest.raises(HTTPException) as exc_info:
                await require_mcp_oauth(credentials=creds)

        assert exc_info.value.status_code == 401
        assert "audience" in exc_info.value.detail.lower()
    finally:
        settings.safecontext_env = original_env


@pytest.mark.asyncio
async def test_mcp_jwt_string_audience_accepted():
    """Audience as a string (not list) that matches 'safecontext-api' → accepted."""
    from config import settings

    original_env = settings.safecontext_env
    settings.safecontext_env = "production"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        fake_payload = {
            "sub": "agent-xyz",
            "aud": "safecontext-api",
            "scope": "mcp:audit",
        }
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")

        with patch("mcp.auth._decode_token", new_callable=AsyncMock) as mock_decode:
            mock_decode.return_value = fake_payload
            result = await require_mcp_oauth(credentials=creds)

        assert result["sub"] == "agent-xyz"
    finally:
        settings.safecontext_env = original_env


@pytest.mark.asyncio
async def test_mcp_dev_mode_static_token():
    """Dev mode: static token matches settings.mcp_auth_token → 200 with dev payload."""
    from config import settings

    original_env = settings.safecontext_env
    original_token = settings.mcp_auth_token
    settings.safecontext_env = "dev"
    settings.mcp_auth_token = "dev-static-secret"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="dev-static-secret")
        result = await require_mcp_oauth(credentials=creds)

        assert result["sub"] == "dev-agent"
        assert result["client_id"] == "dev"
        assert "mcp:scan" in result["scope"]
        assert "mcp:approve" in result["scope"]
    finally:
        settings.safecontext_env = original_env
        settings.mcp_auth_token = original_token


@pytest.mark.asyncio
async def test_mcp_dev_mode_wrong_static_token_falls_through_to_jwt():
    """Dev mode: wrong static token → tries JWT validation → 401."""
    from config import settings

    original_env = settings.safecontext_env
    original_token = settings.mcp_auth_token
    settings.safecontext_env = "dev"
    settings.mcp_auth_token = "dev-static-secret"
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-token")

        with patch("mcp.auth._decode_token", new_callable=AsyncMock) as mock_decode:
            mock_decode.side_effect = HTTPException(status_code=401, detail="Invalid or expired token")
            with pytest.raises(HTTPException) as exc_info:
                await require_mcp_oauth(credentials=creds)

        assert exc_info.value.status_code == 401
    finally:
        settings.safecontext_env = original_env
        settings.mcp_auth_token = original_token


# ── Integration tests against the full app ────────────────────────────────────


def _make_mock_db():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = AsyncMock()
    session.begin = MagicMock(return_value=cm)
    session.add = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    return session


@pytest.fixture(autouse=True)
def override_db():
    """Override get_db for all tests in this file."""
    from db.session import get_db

    mock_db = _make_mock_db()

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_integration_no_token_returns_401():
    """Integration: no Authorization header → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/mcp/tools")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_integration_dev_static_token_lists_tools():
    """Integration: dev mode static token → 200 on /v1/mcp/tools."""
    from config import settings

    original_env = settings.safecontext_env
    original_token = settings.mcp_auth_token
    settings.safecontext_env = "dev"
    settings.mcp_auth_token = "integration-dev-token"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/mcp/tools",
                headers={"Authorization": "Bearer integration-dev-token"},
            )
        assert resp.status_code == 200
        assert "tools" in resp.json()
    finally:
        settings.safecontext_env = original_env
        settings.mcp_auth_token = original_token
