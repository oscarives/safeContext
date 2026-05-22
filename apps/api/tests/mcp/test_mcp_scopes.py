"""Tests T9 — Consent management / scope enforcement for MCP tools.

Covers:
- require_tool_scope unit tests (all tools)
- Integration: mcp:scan allows safecontext.scan, blocks safecontext.approve
- Integration: mcp:scan + mcp:approve allows safecontext.approve
- Integration: unknown tool name passes scope check (router handles 404)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from main import app  # import at module level — same pattern as other MCP test files
from mcp.auth import require_mcp_oauth
from mcp.scopes import TOOL_SCOPES, require_tool_scope


# ── Unit tests for require_tool_scope ─────────────────────────────────────────


def test_require_tool_scope_allows_when_scope_present():
    """Token with required scope → no exception raised."""
    payload = {"sub": "agent-1", "scope": "mcp:scan mcp:classify", "aud": ["safecontext-api"]}
    require_tool_scope("safecontext.scan", payload)  # should not raise
    require_tool_scope("safecontext.classify", payload)  # should not raise


def test_require_tool_scope_raises_403_when_scope_missing():
    """Token missing required scope → 403 HTTPException."""
    payload = {"sub": "agent-1", "scope": "mcp:scan", "aud": ["safecontext-api"]}
    with pytest.raises(HTTPException) as exc_info:
        require_tool_scope("safecontext.approve", payload)
    assert exc_info.value.status_code == 403
    assert "mcp:approve" in exc_info.value.detail


def test_require_tool_scope_unknown_tool_passes():
    """Unknown tool name → no exception (router handles 404)."""
    payload = {"sub": "agent-1", "scope": "", "aud": ["safecontext-api"]}
    require_tool_scope("safecontext.unknown_future_tool", payload)  # should not raise


def test_require_tool_scope_empty_scope_blocks_all_tools():
    """Token with empty scope → 403 for every known tool."""
    payload = {"sub": "agent-1", "scope": "", "aud": ["safecontext-api"]}
    for tool_name in TOOL_SCOPES:
        with pytest.raises(HTTPException) as exc_info:
            require_tool_scope(tool_name, payload)
        assert exc_info.value.status_code == 403


def test_require_tool_scope_missing_scope_key_blocks_all_tools():
    """Token with no scope key at all → 403 for every known tool."""
    payload = {"sub": "agent-1", "aud": ["safecontext-api"]}
    for tool_name in TOOL_SCOPES:
        with pytest.raises(HTTPException) as exc_info:
            require_tool_scope(tool_name, payload)
        assert exc_info.value.status_code == 403


def test_require_tool_scope_all_scopes_grants_all_tools():
    """Token with all MCP scopes → all tools allowed."""
    all_scopes = " ".join(TOOL_SCOPES.values())
    payload = {"sub": "agent-1", "scope": all_scopes, "aud": ["safecontext-api"]}
    for tool_name in TOOL_SCOPES:
        require_tool_scope(tool_name, payload)  # none should raise


@pytest.mark.parametrize("tool_name,required_scope", list(TOOL_SCOPES.items()))
def test_each_tool_requires_its_scope(tool_name, required_scope):
    """Parametrized: each tool requires exactly its declared scope."""
    # Grant only the required scope
    payload = {"sub": "agent-1", "scope": required_scope, "aud": ["safecontext-api"]}
    require_tool_scope(tool_name, payload)  # should not raise

    # Remove the required scope and verify 403
    other_scopes = " ".join(s for s in TOOL_SCOPES.values() if s != required_scope)
    payload_without = {"sub": "agent-1", "scope": other_scopes, "aud": ["safecontext-api"]}
    with pytest.raises(HTTPException) as exc_info:
        require_tool_scope(tool_name, payload_without)
    assert exc_info.value.status_code == 403
    assert required_scope in exc_info.value.detail


# ── Integration tests via /v1/mcp/call dispatch ───────────────────────────────


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
    """Override get_db for all integration tests in this file."""
    from db.session import get_db

    mock_db = _make_mock_db()

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def token_scan_only(monkeypatch):
    """Dev mode token that grants only mcp:scan scope.

    Uses dev-mode static token + patches the dev payload's scope field.
    Follows the same pattern as valid_token in other test files but limits scope.
    """
    from config import settings

    monkeypatch.setenv("MCP_AUTH_TOKEN", "scan-scope-token")
    settings.mcp_auth_token = "scan-scope-token"
    settings.safecontext_env = "dev"

    scan_payload = {
        "sub": "dev-agent",
        "scope": "mcp:scan",  # Only scan scope — no approve
        "client_id": "dev",
        "_raw_token": "scan-scope-token",
    }

    # Use dependency_overrides — this is the correct FastAPI testing pattern
    async def _mock_scan_only(credentials=None):
        return scan_payload

    app.dependency_overrides[require_mcp_oauth] = _mock_scan_only
    yield "scan-scope-token"
    app.dependency_overrides.pop(require_mcp_oauth, None)
    settings.safecontext_env = "production"


@pytest.fixture
def token_all_scopes(monkeypatch):
    """Dev mode token that grants all MCP scopes."""
    from config import settings

    monkeypatch.setenv("MCP_AUTH_TOKEN", "all-scopes-token")
    settings.mcp_auth_token = "all-scopes-token"
    settings.safecontext_env = "dev"

    all_scopes = "mcp:scan mcp:sanitize mcp:classify mcp:audit mcp:policy mcp:approve"
    full_payload = {
        "sub": "dev-agent",
        "scope": all_scopes,
        "client_id": "dev",
        "_raw_token": "all-scopes-token",
    }

    async def _mock_all(credentials=None):
        return full_payload

    app.dependency_overrides[require_mcp_oauth] = _mock_all
    yield "all-scopes-token"
    app.dependency_overrides.pop(require_mcp_oauth, None)
    settings.safecontext_env = "production"


@pytest.mark.asyncio
async def test_scan_scope_allows_scan_tool(token_scan_only):
    """Token with mcp:scan scope can invoke safecontext.scan."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            json={
                "tool": "safecontext.scan",
                "tool_version": "1.0.0",
                "input": {"document": "hello world", "policy_name": "base"},
            },
            headers={"Authorization": f"Bearer {token_scan_only}"},
        )
    # Should succeed (200), not 403
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["tool"] == "safecontext.scan"


@pytest.mark.asyncio
async def test_scan_scope_blocks_approve_tool(token_scan_only):
    """Token with only mcp:scan scope cannot invoke safecontext.approve → 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            json={
                "tool": "safecontext.approve",
                "tool_version": "1.1.0",
                "input": {
                    "finding_id": "00000000-0000-0000-0000-000000000001",
                    "decision": "approve",
                    "justification": "test",
                    "agent_client_id": "test-agent",
                },
            },
            headers={"Authorization": f"Bearer {token_scan_only}"},
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    assert "mcp:approve" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_scope_allows_approve_tool(token_all_scopes):
    """Token with all scopes can invoke safecontext.approve (gets past scope check)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            json={
                "tool": "safecontext.approve",
                "tool_version": "1.1.0",
                "input": {
                    "finding_id": "00000000-0000-0000-0000-000000000001",
                    "decision": "approve",
                    "justification": "test",
                    "agent_client_id": "test-agent",
                },
            },
            headers={"Authorization": f"Bearer {token_all_scopes}"},
        )
    # Not 403 — the scope check passes. The 404 is from "finding not found" business logic.
    assert resp.status_code != 403, f"Got unexpected 403: {resp.text}"
