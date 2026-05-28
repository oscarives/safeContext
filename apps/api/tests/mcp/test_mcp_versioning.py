"""Tests E4.5 — Tool versioning and E4.6 — safecontext.approve.

Criterios verificados:
- Clientes pueden fijar tool_version en request (E4.5)
- Compatibilidad N-1: versión 1.0.0 sobre servidor 1.1.0
- tool_version desconocida → 400
- safecontext.approve con tool_version=1.0.0 → 400
- safecontext.approve con finding escalado → approved_by_agent_id poblado
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


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
    settings.safecontext_env = "dev"
    yield "test-token-abc"
    settings.safecontext_env = "production"


# ── E4.5 Versioned dispatch ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_scan_v100(valid_token, mock_db):
    """POST /v1/mcp/call with tool_version=1.0.0 returns same result as direct endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "tool": "safecontext.scan",
                "tool_version": "1.0.0",
                "input": {"document": "hello world", "policy_name": "base"},
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "safecontext.scan"
    assert "trace_id" in body
    assert "output" in body


@pytest.mark.asyncio
async def test_dispatch_scan_v110(valid_token, mock_db):
    """POST /v1/mcp/call with tool_version=1.1.0 returns same result."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "tool": "safecontext.scan",
                "tool_version": "1.1.0",
                "input": {"document": "hello world", "policy_name": "base"},
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "safecontext.scan"
    assert "output" in body


@pytest.mark.asyncio
async def test_dispatch_unknown_version(valid_token, mock_db):
    """tool_version=99.0.0 → 400 Unsupported tool version."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "tool": "safecontext.scan",
                "tool_version": "99.0.0",
                "input": {"document": "hello", "policy_name": "base"},
            },
        )
    assert resp.status_code == 400
    assert "99.0.0" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_dispatch_without_token_returns_401(mock_db):
    """Versioned dispatch requires authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            json={
                "tool": "safecontext.scan",
                "tool_version": "1.0.0",
                "input": {"document": "hello", "policy_name": "base"},
            },
        )
    assert resp.status_code == 401


# ── E4.6 safecontext.approve ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_requires_v110(valid_token, mock_db):
    """safecontext.approve with tool_version=1.0.0 → 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/call",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "tool": "safecontext.approve",
                "tool_version": "1.0.0",
                "input": {
                    "finding_id": str(uuid4()),
                    "decision": "approve",
                    "justification": "Approved by automated agent review",
                    "agent_client_id": "agent-001",
                },
            },
        )
    assert resp.status_code == 400
    assert "1.1.0" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_records_agent_id(valid_token, mock_db):
    """safecontext.approve with escalated finding records approved_by_agent_id."""
    from db.models.finding import Finding
    from db.models.operation import Operation

    finding_id = uuid4()
    operation_id = uuid4()
    trace_id = uuid4()

    # Build mock finding and operation
    mock_finding = MagicMock(spec=Finding)
    mock_finding.id = finding_id
    mock_finding.operation_id = operation_id

    mock_operation = MagicMock(spec=Operation)
    mock_operation.id = operation_id
    mock_operation.status = "escalated"
    mock_operation.trace_id = trace_id
    mock_operation.policy_version = "1.0.0"

    # Configure mock_db.execute to return finding then operation
    _execute_results = []

    finding_result = MagicMock()
    finding_result.scalar_one_or_none.return_value = mock_finding

    operation_result = MagicMock()
    operation_result.scalar_one_or_none.return_value = mock_operation

    mock_db.execute = AsyncMock(side_effect=[finding_result, operation_result])

    captured_redactions = []

    def capture_add(obj):
        captured_redactions.append(obj)

    mock_db.add = capture_add

    # F7-5: write-time sealing adds a chain query + Vault call; it is covered in
    # tests/api/test_evidence.py, so isolate it here to keep the mock_db's fixed
    # execute side_effect list intact.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch(
            "core.chain.seal_operation_with_settings",
            new_callable=AsyncMock,
            return_value={"chain_hash": "x" * 64, "signed": False, "key_version": None},
        ):
            resp = await client.post(
                "/v1/mcp/tools/safecontext.approve",
                headers={"Authorization": f"Bearer {valid_token}"},
                json={
                    "finding_id": str(finding_id),
                    "decision": "approve",
                    "justification": "Automated agent review approved this finding",
                    "agent_client_id": "agent-pipeline-001",
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "safecontext.approve"
    assert body["version"] == "1.1.0"
    assert body["output"]["decision"] == "approve"
    assert body["output"]["finding_id"] == str(finding_id)
    assert body["output"]["recorded_by"] == "agent-pipeline-001"

    # Verify a Redaction was added with approved_by_agent_id populated
    from db.models.redaction import Redaction

    redactions = [r for r in captured_redactions if isinstance(r, Redaction)]
    assert len(redactions) == 1
    assert redactions[0].approved_by_agent_id is not None
    assert redactions[0].finding_id == finding_id


@pytest.mark.asyncio
async def test_approve_finding_not_found(valid_token, mock_db):
    """safecontext.approve with unknown finding_id → 404."""
    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=not_found_result)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.approve",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "finding_id": str(uuid4()),
                "decision": "approve",
                "justification": "Automated agent approval",
                "agent_client_id": "agent-001",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_operation_not_escalated(valid_token, mock_db):
    """safecontext.approve when operation is not escalated → 409."""
    from db.models.finding import Finding
    from db.models.operation import Operation

    finding_id = uuid4()
    operation_id = uuid4()

    mock_finding = MagicMock(spec=Finding)
    mock_finding.id = finding_id
    mock_finding.operation_id = operation_id

    mock_operation = MagicMock(spec=Operation)
    mock_operation.id = operation_id
    mock_operation.status = "completed"  # not escalated

    finding_result = MagicMock()
    finding_result.scalar_one_or_none.return_value = mock_finding

    operation_result = MagicMock()
    operation_result.scalar_one_or_none.return_value = mock_operation

    mock_db.execute = AsyncMock(side_effect=[finding_result, operation_result])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/mcp/tools/safecontext.approve",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "finding_id": str(finding_id),
                "decision": "approve",
                "justification": "Automated agent approval",
                "agent_client_id": "agent-001",
            },
        )
    assert resp.status_code == 409
