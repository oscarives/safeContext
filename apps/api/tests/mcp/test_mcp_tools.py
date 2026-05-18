"""Tests E1.4 — MCP Server acceptance criteria."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _fake_db_gen(session):
    yield session


def make_mock_db():
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


@pytest.fixture
def mock_db():
    return make_mock_db()


@pytest.fixture(autouse=True)
def override_db(mock_db):
    """Override get_db for all tests in this file."""
    from db.session import get_db

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def valid_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token-abc")
    from config import settings
    settings.mcp_auth_token = "test-token-abc"
    return "test-token-abc"


# ── Authentication ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_without_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.scan",
            json={"document": "hello", "policy_name": "base"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sanitize_without_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.sanitize",
            json={"trace_id": str(uuid4()), "redaction_type": "mask"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_classify_without_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.classify",
            json={"document": "hello world"},
        )
    assert resp.status_code == 401


# ── Tool schemas ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tools_returns_three_tools(valid_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/mcp/tools",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    tool_names = {t["name"] for t in tools}
    assert {"safecontext.scan", "safecontext.sanitize", "safecontext.classify"}.issubset(tool_names)
    assert len(tool_names) >= 3


@pytest.mark.asyncio
async def test_tools_have_version_field(valid_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/mcp/tools",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 200
    for tool in resp.json()["tools"]:
        assert "version" in tool
        assert tool["version"] in {"1.0.0", "1.1.0"}


# ── safecontext.scan ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_returns_trace_id_in_body_and_header(valid_token, mock_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.scan",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"document": "Contact alice@example.com", "policy_name": "base"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "trace_id" in body
    assert "X-Trace-ID" in resp.headers


@pytest.mark.asyncio
async def test_scan_result_has_mcp_tool_envelope(valid_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.scan",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"document": "test doc", "policy_name": "base"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "safecontext.scan"
    assert body["version"] in {"1.0.0", "1.1.0"}
    assert "output" in body


@pytest.mark.asyncio
async def test_scan_records_actor_type_mcp_agent(valid_token, mock_db):
    captured = []
    mock_db.add = lambda obj: captured.append(obj)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/v1/mcp/tools/safecontext.scan",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"document": "document text", "policy_name": "base"},
        )

    from db.models.operation import Operation
    operations = [o for o in captured if isinstance(o, Operation)]
    assert len(operations) == 1
    assert operations[0].actor_type == "mcp_agent"


# ── safecontext.classify ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classify_returns_sensitivity_level(valid_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.classify",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"document": "This document contains a password: secret123"},
        )
    assert resp.status_code == 200
    output = resp.json()["output"]
    assert output["overall_level"] in {"public", "internal", "confidential", "restricted"}
    assert len(output["sections"]) >= 1
    for section in output["sections"]:
        assert "level" in section
        assert "justification" in section


@pytest.mark.asyncio
async def test_classify_restricted_for_credential_content(valid_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.classify",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"document": "API_KEY=sk-1234 password=hunter2"},
        )
    assert resp.status_code == 200
    assert resp.json()["output"]["overall_level"] == "restricted"
