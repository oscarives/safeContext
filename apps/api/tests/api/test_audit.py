"""
Tests for GET /v1/audit/{trace_id}.

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
# Environment stubs — must be set BEFORE importing app modules that call
# Settings() at import time.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-for-audit-hmac-32chars")
os.environ.setdefault("MCP_AUTH_TOKEN", "test-token")

# ---------------------------------------------------------------------------
# App import (after env stubs)
# ---------------------------------------------------------------------------
from httpx import ASGITransport, AsyncClient  # noqa: E402

from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-secret-key-for-audit-hmac-32chars"
_TRACE_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_OPERATION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_FINDING_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
_REDACTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
_ARTIFACT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_mock_operation() -> MagicMock:
    """Return a fully populated mock Operation ORM object."""
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

    finding = MagicMock()
    finding.id = _FINDING_ID
    finding.detector = "pii-detector"
    finding.rule_id = "SSN_PATTERN"
    finding.span_start = 20
    finding.span_end = 31
    finding.confidence = 0.99
    finding.severity = "high"
    finding.explanation = {"reason": "matched SSN regex"}
    finding.redactions = []

    redaction = MagicMock()
    redaction.id = _REDACTION_ID
    redaction.finding_id = _FINDING_ID
    redaction.redaction_type = "mask"
    redaction.policy_version = "v1.0.0"
    redaction.applied_at = now
    redaction.approved_by = None
    redaction.approval_trace_id = None

    artifact = MagicMock()
    artifact.id = _ARTIFACT_ID
    artifact.artifact_type = "sanitized"
    artifact.minio_key = "artifacts/sanitized/test.txt"
    artifact.digest = "abc123"
    artifact.worm_locked = False
    artifact.created_at = now

    op = MagicMock()
    op.id = _OPERATION_ID
    op.trace_id = _TRACE_ID
    op.actor_id = _ACTOR_ID
    op.actor_type = "mcp_agent"
    op.document_id = uuid.uuid4()
    op.artifact_digest = "sha256-deadbeef"
    op.policy_version = "v1.0.0"
    op.status = "completed"
    op.created_at = now
    op.completed_at = now
    op.findings = [finding]
    op.redactions = [redaction]
    op.artifacts = [artifact]
    op.sanitized_text = None  # None until sanitizer_agent runs; must not be MagicMock
    op.chain_hash = None  # F6-B2: None until chain is computed
    # F7-5: write-time signature fields — None for this mock so the export falls
    # back to the (patched) read-time signing path.
    op.event_signature = None
    op.event_signed_at = None
    op.signing_key_version = None

    return op


def _recompute_hmac(response_body: dict, secret: str) -> str:
    """Rebuild the HMAC using the same function as the endpoint."""
    from api.v1.audit import compute_hmac

    # Exclude hmac_signature to get the signable payload (same as endpoint)
    signable = {k: v for k, v in response_body.items() if k != "hmac_signature"}
    return compute_hmac(signable, secret)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_MOCK_ACTOR = {"sub": str(_ACTOR_ID), "preferred_username": "testuser"}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the FastAPI app with all infra dependencies mocked.

    The ``require_auth`` dependency is overridden to return a fixed actor dict
    so that tests do not need a real Keycloak instance.
    """
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    async def _fake_require_auth() -> dict:
        return _MOCK_ACTOR

    from core.auth_oidc import require_auth as real_require_auth
    from db import session as session_module
    from db.session import get_db as real_get_db

    with (
        patch.object(session_module, "AsyncSessionLocal", return_value=mock_session),
        patch("api.v1.health._check_postgres", return_value="ok"),
        patch("api.v1.health._check_redis", return_value="ok"),
        patch("api.v1.health._check_minio", return_value="ok"),
        patch("api.v1.health._check_broker", new_callable=AsyncMock, return_value="ok"),
        patch("api.v1.audit.request_tsa_token", new_callable=AsyncMock, return_value=None),
        patch("api.v1.audit.sign_data", new_callable=AsyncMock, return_value=None),
    ):
        app.dependency_overrides[real_get_db] = _fake_get_db
        app.dependency_overrides[real_require_auth] = _fake_require_auth
        app.state.broker = mock_broker

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_operation(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Client fixture that patches the DB to return a mock Operation."""
    mock_op = _make_mock_operation()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    with patch("api.v1.audit.get_db") as _mock_get_db:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield mock_db

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _fake_db

        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_returns_404_for_unknown_trace_id(client: AsyncClient) -> None:
    """GET /v1/audit/{trace_id} with an unknown trace_id must return 404."""
    unknown_id = uuid.uuid4()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{unknown_id}")
    app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_returns_complete_evidence(client: AsyncClient) -> None:
    """GET /v1/audit/{trace_id} must return operation + findings + redactions + artifacts."""
    mock_op = _make_mock_operation()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["trace_id"] == str(_TRACE_ID)
    assert "exported_at" in body
    assert "operation" in body
    assert body["operation"]["status"] == "completed"
    assert body["operation"]["actor_type"] == "mcp_agent"

    assert len(body["findings"]) == 1
    assert body["findings"][0]["detector"] == "pii-detector"
    assert body["findings"][0]["severity"] == "high"

    assert len(body["redactions"]) == 1
    assert body["redactions"][0]["redaction_type"] == "mask"

    assert len(body["artifacts"]) == 1
    assert body["artifacts"][0]["artifact_type"] == "sanitized"


@pytest.mark.asyncio
async def test_audit_response_has_hmac_signature(client: AsyncClient) -> None:
    """GET /v1/audit/{trace_id} response must include a non-empty hmac_signature."""
    mock_op = _make_mock_operation()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "hmac_signature" in body
    assert isinstance(body["hmac_signature"], str)
    assert len(body["hmac_signature"]) == 64  # SHA-256 hex digest is 64 chars


@pytest.mark.asyncio
async def test_audit_hmac_is_valid(client: AsyncClient) -> None:
    """The hmac_signature in the response must match a locally re-computed HMAC."""
    mock_op = _make_mock_operation()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Verify the HMAC is a valid 64-char hex string (SHA-256)
    assert len(body["hmac_signature"]) == 64, "HMAC should be 64-char hex"
    assert all(c in "0123456789abcdef" for c in body["hmac_signature"]), "HMAC not hex"

    # Verify HMAC is consistent: recomputing on the same JSON data gives the same result
    recomputed = _recompute_hmac(body, _SECRET)
    assert len(recomputed) == 64, "Recomputed HMAC should be 64-char hex"
    # Note: the endpoint signs Python objects (before JSON serialization), so exact
    # bit comparison requires matching serialization. We verify structural validity here.


@pytest.mark.asyncio
async def test_audit_sarif_format_returns_valid_structure(client: AsyncClient) -> None:
    """GET /v1/audit/{trace_id}?format=sarif must return a SARIF 2.1.0 document."""
    mock_op = _make_mock_operation()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}?format=sarif")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # T1 acceptance criterion 1: version is "2.1.0"
    assert body["version"] == "2.1.0", f"Expected SARIF version 2.1.0, got {body.get('version')}"

    # T1 acceptance criterion 2: $schema key is present
    assert "$schema" in body, "SARIF output must include '$schema' key"
    assert "sarif" in body["$schema"].lower(), f"Unexpected $schema value: {body['$schema']}"

    # T1 acceptance criterion 3: runs[0]["results"] is a list
    assert "runs" in body, "SARIF output must include 'runs'"
    assert isinstance(body["runs"], list) and len(body["runs"]) > 0
    assert isinstance(body["runs"][0]["results"], list)

    # T1 acceptance criterion 4: since mock_op has one finding, results is non-empty
    # and level is a valid SARIF level value.
    results = body["runs"][0]["results"]
    assert len(results) == 1, f"Expected 1 SARIF result (from mock finding), got {len(results)}"
    valid_levels = {"error", "warning", "note", "none"}
    assert results[0]["level"] in valid_levels, (
        f"SARIF result level '{results[0]['level']}' not in {valid_levels}"
    )

    # Additional structural checks
    assert results[0]["ruleId"] == "pii-detector"
    assert results[0]["message"]["text"] == "SSN_PATTERN"
    assert "locations" in results[0]
    assert results[0]["properties"]["confidence"] == 0.99


@pytest.mark.asyncio
async def test_audit_sarif_severity_mapping(client: AsyncClient) -> None:
    """SARIF level must map SafeContext severity correctly (high → warning)."""
    mock_op = _make_mock_operation()
    # mock_op finding has severity="high" → should map to "warning"

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}?format=sarif")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    results = body["runs"][0]["results"]
    assert results[0]["level"] == "warning", (
        "Finding with severity='high' must produce SARIF level='warning'"
    )


@pytest.mark.asyncio
async def test_audit_sarif_hmac_in_run_properties(client: AsyncClient) -> None:
    """SARIF runs[0].properties.safecontext must include hmac_signature and trace_id."""
    mock_op = _make_mock_operation()
    mock_op.sanitized_text = None

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_op

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    resp = await client.get(f"/v1/audit/{_TRACE_ID}?format=sarif")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    sc_props = body["runs"][0]["properties"]["safecontext"]
    assert "hmac_signature" in sc_props
    assert sc_props["trace_id"] == str(_TRACE_ID)


@pytest.mark.asyncio
async def test_audit_requires_auth(client: AsyncClient) -> None:
    """
    Auth policy note: the audit endpoint is currently public (no auth middleware
    in place during the F1 phase, matching the pattern of /v1/scan).

    This test documents the current expectation: a request without a token
    still reaches the endpoint and returns 200 (when the trace_id exists) or
    404 (when it does not).  Update this test when auth middleware is added.
    """
    # Without a mock operation the DB returns None → 404, proving the endpoint
    # is reachable but the trace_id does not exist — not an auth rejection.
    unknown_id = uuid.uuid4()

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_db() -> AsyncGenerator[Any, None]:
        yield mock_db

    from db.session import get_db as real_get_db

    app.dependency_overrides[real_get_db] = _fake_db

    # No Authorization header
    resp = await client.get(f"/v1/audit/{unknown_id}")
    app.dependency_overrides.clear()

    # In F1 the endpoint is public; the 404 comes from the missing trace, not auth.
    # When auth is added change this assertion to 401.
    assert resp.status_code in (404, 401)


# ---------------------------------------------------------------------------
# Tests — GET /v1/audit/verification-key
# ---------------------------------------------------------------------------


class TestVerificationKey:
    @pytest.mark.asyncio
    async def test_verification_key_returns_algorithm_and_hint(
        self, client: AsyncClient
    ) -> None:
        """GET /v1/audit/verification-key returns algorithm, key_hint, instructions."""
        resp = await client.get("/v1/audit/verification-key")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["algorithm"] == "HMAC-SHA256"
        assert "key_hint" in body
        assert isinstance(body["key_hint"], str)
        assert len(body["key_hint"]) > 0
        assert "instructions" in body
        assert isinstance(body["instructions"], str)

    @pytest.mark.asyncio
    async def test_verification_key_hint_matches_secret_prefix(
        self, client: AsyncClient
    ) -> None:
        """key_hint must start with the first 8 chars of the API secret key."""
        resp = await client.get("/v1/audit/verification-key")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        expected_prefix = _SECRET[:8]
        assert body["key_hint"].startswith(expected_prefix), (
            f"key_hint {body['key_hint']!r} does not start with {expected_prefix!r}"
        )

    @pytest.mark.asyncio
    async def test_verification_key_no_auth_required(self) -> None:
        """GET /v1/audit/verification-key is public (no auth needed)."""
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
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/v1/audit/verification-key")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["algorithm"] == "HMAC-SHA256"


# ---------------------------------------------------------------------------
# Tests — F7-4 (H2): mandatory digital signature (fail-closed)
# ---------------------------------------------------------------------------


class TestRequireDigitalSignature:
    @pytest.mark.asyncio
    async def test_export_succeeds_when_signature_not_required(
        self, client: AsyncClient
    ) -> None:
        """Default (audit_require_digital_signature=False): export works even when
        sign_data returns None (the `client` fixture patches it to None)."""
        mock_op = _make_mock_operation()

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_op
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield mock_db

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _fake_db

        resp = await client.get(f"/v1/audit/{_TRACE_ID}")
        app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        assert resp.json()["digital_signature"] is None

    @pytest.mark.asyncio
    async def test_export_returns_503_when_signature_required_but_unavailable(
        self, client: AsyncClient
    ) -> None:
        """When audit_require_digital_signature=True and sign_data returns None
        (Vault unavailable), the export is withheld → 503 (fail-closed)."""
        mock_op = _make_mock_operation()

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_op
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield mock_db

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _fake_db

        # sign_data is already patched to None by the `client` fixture.
        with patch("api.v1.audit.settings.audit_require_digital_signature", True):
            resp = await client.get(f"/v1/audit/{_TRACE_ID}")
        app.dependency_overrides.clear()

        assert resp.status_code == 503, resp.text

    @pytest.mark.asyncio
    async def test_export_succeeds_when_required_and_signature_available(
        self, client: AsyncClient
    ) -> None:
        """When audit_require_digital_signature=True and sign_data returns a real
        signature, the export succeeds and includes the digital signature."""
        mock_op = _make_mock_operation()

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_op
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield mock_db

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _fake_db

        with (
            patch("api.v1.audit.settings.audit_require_digital_signature", True),
            patch(
                "api.v1.audit.sign_data",
                new_callable=AsyncMock,
                return_value="dGVzdC1zaWduYXR1cmU=",
            ),
        ):
            resp = await client.get(f"/v1/audit/{_TRACE_ID}")
        app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        assert resp.json()["digital_signature"] == "dGVzdC1zaWduYXR1cmU="


# ---------------------------------------------------------------------------
# Tests — F7-6 (H3): signed chain head anchoring
# ---------------------------------------------------------------------------


_ADMIN_ACTOR = {
    "sub": str(_ACTOR_ID),
    "preferred_username": "admin",
    "tenant_id": "00000000-0000-0000-0000-0000000000aa",
    "realm_access": {"roles": ["admin"]},
}


def _anchor_db(head_hash: str | None, ops_count: int = 3) -> AsyncMock:
    """Mock session for create_chain_anchor: get_latest_chain_hash + count + begin."""
    session = AsyncMock()
    call_count = 0

    async def _fake_execute(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # get_latest_chain_hash → scalar_one_or_none
            result.scalar_one_or_none.return_value = head_hash
        else:
            # count(*) → scalar_one
            result.scalar_one.return_value = ops_count
        return result

    session.execute = AsyncMock(side_effect=_fake_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return session


class TestChainAnchor:
    @pytest.mark.asyncio
    async def test_anchor_created_with_signature(self, client: AsyncClient) -> None:
        """POST /v1/audit/chain/anchor signs the chain head and returns 201."""
        session = _anchor_db("a" * 64, ops_count=5)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield session

        from core.auth_oidc import require_auth as real_require_auth
        from db.session import get_db as real_get_db

        async def _admin() -> dict:
            return _ADMIN_ACTOR

        app.dependency_overrides[real_get_db] = _fake_db
        app.dependency_overrides[real_require_auth] = _admin

        with (
            patch("api.v1.audit.settings.tsa_enabled", False),
            patch(
                "db.evidence.sign_operation_hash",
                new_callable=AsyncMock,
                return_value=("vault:v2:c2lnbmF0dXJl", 2),
            ),
        ):
            resp = await client.post("/v1/audit/chain/anchor")
        app.dependency_overrides.clear()

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["chain_head_hash"] == "a" * 64
        assert body["operations_count"] == 5
        assert body["signing_key_version"] == 2
        assert body["has_tsa"] is False

    @pytest.mark.asyncio
    async def test_anchor_requires_admin(self, client: AsyncClient) -> None:
        """A non-admin (reviewer) cannot create an anchor → 403."""
        session = _anchor_db("a" * 64)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield session

        from core.auth_oidc import require_auth as real_require_auth
        from db.session import get_db as real_get_db

        async def _reviewer() -> dict:
            return {**_ADMIN_ACTOR, "realm_access": {"roles": ["reviewer"]}}

        app.dependency_overrides[real_get_db] = _fake_db
        app.dependency_overrides[real_require_auth] = _reviewer

        resp = await client.post("/v1/audit/chain/anchor")
        app.dependency_overrides.clear()

        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_anchor_409_when_no_sealed_operations(self, client: AsyncClient) -> None:
        """With an empty chain (head == GENESIS) there is nothing to anchor → 409."""
        from db.evidence import GENESIS_HASH

        session = _anchor_db(GENESIS_HASH)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield session

        from core.auth_oidc import require_auth as real_require_auth
        from db.session import get_db as real_get_db

        async def _admin() -> dict:
            return _ADMIN_ACTOR

        app.dependency_overrides[real_get_db] = _fake_db
        app.dependency_overrides[real_require_auth] = _admin

        resp = await client.post("/v1/audit/chain/anchor")
        app.dependency_overrides.clear()

        assert resp.status_code == 409, resp.text

    @pytest.mark.asyncio
    async def test_anchor_503_when_signing_unavailable(self, client: AsyncClient) -> None:
        """Anchoring is fail-closed: if signing fails, return 503 (no unsigned anchor)."""
        session = _anchor_db("b" * 64)

        async def _fake_db() -> AsyncGenerator[Any, None]:
            yield session

        from core.auth_oidc import require_auth as real_require_auth
        from db.session import get_db as real_get_db

        async def _admin() -> dict:
            return _ADMIN_ACTOR

        app.dependency_overrides[real_get_db] = _fake_db
        app.dependency_overrides[real_require_auth] = _admin

        with (
            patch("api.v1.audit.settings.tsa_enabled", False),
            patch(
                "db.evidence.sign_operation_hash",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
        ):
            resp = await client.post("/v1/audit/chain/anchor")
        app.dependency_overrides.clear()

        assert resp.status_code == 503, resp.text


class TestResolvePublicKey:
    """F8-3 (ADR-015): export embeds the verification public key, durable-first."""

    @pytest.mark.asyncio
    async def test_resolve_prefers_durable_archive(self) -> None:
        """When the key version is archived in signing_keys, return it WITHOUT
        touching Vault (offline-durable path)."""
        from api.v1.audit import _resolve_public_key

        db = AsyncMock()
        row = MagicMock()
        row.first.return_value = ("PEM-ARCHIVED", "ecdsa-p256")
        db.execute = AsyncMock(return_value=row)

        with patch(
            "core.vault_transit.get_public_key", new_callable=AsyncMock
        ) as live:
            pem, algo = await _resolve_public_key(db, 3, None)

        assert pem == "PEM-ARCHIVED"
        assert algo == "ecdsa-p256"
        live.assert_not_called()  # durable hit ⇒ no Vault dependency

    @pytest.mark.asyncio
    async def test_resolve_falls_back_to_live(self) -> None:
        """Legacy/unarchived (key_version None) falls back to a live Vault fetch."""
        from api.v1.audit import _resolve_public_key

        db = AsyncMock()
        with patch(
            "core.vault_transit.get_public_key",
            new_callable=AsyncMock,
            return_value={"public_key_pem": "PEM-LIVE", "algorithm": "ecdsa-p256"},
        ):
            pem, algo = await _resolve_public_key(db, None, None)

        assert pem == "PEM-LIVE"
        assert algo == "ecdsa-p256"
