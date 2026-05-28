"""
Tests for /v1/review endpoints (pending, approve, reject).

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
# Environment stubs
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

_REVIEWER_SUB = "550e8400-e29b-41d4-a716-446655440000"
_VIEWER_SUB = "660e8400-e29b-41d4-a716-446655440000"
_FINDING_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
_OPERATION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_TRACE_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_finding(
    *,
    finding_id: uuid.UUID = _FINDING_ID,
    operation_status: str = "escalated",
) -> MagicMock:
    operation = MagicMock()
    operation.id = _OPERATION_ID
    operation.trace_id = _TRACE_ID
    operation.status = operation_status
    operation.policy_version = "v1.0.0"
    operation.created_at = _NOW
    operation.completed_at = None
    operation.findings = []

    finding = MagicMock()
    finding.id = finding_id
    finding.operation_id = _OPERATION_ID
    finding.operation = operation
    finding.detector = "pii-detector"
    finding.rule_id = "SSN_PATTERN"
    finding.confidence = 0.99
    finding.severity = "high"
    finding.span_start = 20
    finding.span_end = 31
    finding.explanation = {"reason": "matched SSN regex"}

    return finding


def _make_db_for_load_finding(finding: MagicMock | None) -> AsyncMock:
    """Mock session for _load_escalated_finding: execute → scalar_one_or_none."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    result = MagicMock()
    result.scalar_one_or_none.return_value = finding

    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    return session


def _make_db_for_approve(
    finding: MagicMock,
    total_findings: int = 1,
    total_redactions: int = 1,
) -> AsyncMock:
    """Mock session for approve_finding: load finding, then lock + count in transaction."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.flush = AsyncMock()

    call_count = 0

    async def _fake_execute(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        result = MagicMock()

        if call_count == 1:
            # _load_escalated_finding: select(Finding)
            result.scalar_one_or_none.return_value = finding
        elif call_count == 2:
            # Lock: select(Operation).with_for_update()
            result.scalar_one.return_value = finding.operation
        elif call_count == 3:
            # Count findings
            result.scalar_one.return_value = total_findings
        elif call_count == 4:
            # Count redactions
            result.scalar_one.return_value = total_redactions
        return result

    session.execute = AsyncMock(side_effect=_fake_execute)

    session.begin = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    return session


def _make_db_for_pending(
    operations: list[MagicMock] | None = None,
    outbox_rows: list[MagicMock] | None = None,
) -> AsyncMock:
    """Mock session for get_pending_reviews: 2 queries (operations + outbox)."""
    if operations is None:
        operations = []
    if outbox_rows is None:
        outbox_rows = []

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    async def _fake_execute(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        scalars = MagicMock()

        if call_count == 1:
            scalars.all.return_value = operations
        else:
            scalars.all.return_value = outbox_rows

        result.scalars.return_value = scalars
        return result

    session.execute = AsyncMock(side_effect=_fake_execute)
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def reviewer_client() -> AsyncGenerator[AsyncClient, None]:
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    async def _fake_require_reviewer() -> dict:
        return {
            "sub": _REVIEWER_SUB,
            "realm_access": {"roles": ["reviewer"]},
        }

    async def _fake_require_auth() -> dict:
        return {
            "sub": _REVIEWER_SUB,
            "realm_access": {"roles": ["reviewer"]},
        }

    from core.auth_oidc import require_auth as real_require_auth
    from core.auth_oidc import require_reviewer as real_require_reviewer
    from db import session as session_module
    from db.session import get_db as real_get_db

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

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
        app.dependency_overrides[real_require_reviewer] = _fake_require_reviewer
        app.dependency_overrides[real_require_auth] = _fake_require_auth
        app.state.broker = mock_broker

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient authenticated as viewer (no reviewer role)."""
    mock_broker = AsyncMock()
    mock_broker.enqueue = AsyncMock()

    async def _fake_require_auth() -> dict:
        return {
            "sub": _VIEWER_SUB,
            "realm_access": {"roles": ["viewer"]},
        }

    from core.auth_oidc import require_auth as real_require_auth
    from db import session as session_module
    from db.session import get_db as real_get_db

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

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
# Tests — GET /v1/review/pending
# ---------------------------------------------------------------------------


class TestGetPendingReviews:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_escalated(self, reviewer_client: AsyncClient) -> None:
        """GET /v1/review/pending with no escalated operations returns empty list."""
        session = _make_db_for_pending(operations=[], outbox_rows=[])

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.get("/v1/review/pending")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    @pytest.mark.asyncio
    async def test_returns_escalated_findings_with_correct_shape(
        self, reviewer_client: AsyncClient
    ) -> None:
        """GET /v1/review/pending returns findings from escalated operations."""
        finding = MagicMock()
        finding.id = _FINDING_ID
        finding.detector = "pii-detector"
        finding.rule_id = "SSN_PATTERN"
        finding.confidence = 0.99
        finding.severity = "high"
        finding.span_start = 20
        finding.span_end = 31
        finding.explanation = {"reason": "test"}

        operation = MagicMock()
        operation.id = _OPERATION_ID
        operation.trace_id = _TRACE_ID
        operation.status = "escalated"
        operation.created_at = _NOW
        operation.findings = [finding]

        session = _make_db_for_pending(operations=[operation], outbox_rows=[])

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.get("/v1/review/pending")
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

        item = body["items"][0]
        assert item["finding_id"] == str(_FINDING_ID)
        assert item["trace_id"] == str(_TRACE_ID)
        assert item["detector"] == "pii-detector"
        assert item["severity"] == "high"

    @pytest.mark.asyncio
    async def test_requires_reviewer_role(self, viewer_client: AsyncClient) -> None:
        """GET /v1/review/pending with viewer role returns 403."""
        resp = await viewer_client.get("/v1/review/pending")
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_requires_auth(self) -> None:
        """GET /v1/review/pending without a token returns 401."""
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
                resp = await ac.get("/v1/review/pending")

        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Tests — POST /v1/review/{finding_id}/approve
# ---------------------------------------------------------------------------


class TestApproveFinding:
    @pytest.mark.asyncio
    async def test_approve_creates_redaction_and_completes(
        self, reviewer_client: AsyncClient
    ) -> None:
        """POST /v1/review/{id}/approve creates Redaction and returns approved."""
        finding = _make_mock_finding(operation_status="escalated")
        session = _make_db_for_approve(finding, total_findings=1, total_redactions=1)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        # F7-5: write-time sealing is exercised in tests/api/test_evidence.py;
        # here we isolate the endpoint logic from Vault/chain I/O.
        with patch(
            "core.chain.seal_operation_with_settings",
            new_callable=AsyncMock,
            return_value={"chain_hash": "x" * 64, "signed": False, "key_version": None},
        ):
            resp = await reviewer_client.post(
                f"/v1/review/{_FINDING_ID}/approve",
                json={"justification": "Approved after manual review of the document"},
            )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "approved"
        assert body["trace_id"] == str(_TRACE_ID)

    @pytest.mark.asyncio
    async def test_approve_finding_not_found_returns_404(
        self, reviewer_client: AsyncClient
    ) -> None:
        """POST /v1/review/{id}/approve with unknown finding_id returns 404."""
        session = _make_db_for_load_finding(finding=None)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.post(
            f"/v1/review/{uuid.uuid4()}/approve",
            json={"justification": "Approved after manual review of the document"},
        )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_approve_non_escalated_returns_409(
        self, reviewer_client: AsyncClient
    ) -> None:
        """POST /v1/review/{id}/approve on non-escalated operation returns 409."""
        finding = _make_mock_finding(operation_status="completed")
        session = _make_db_for_load_finding(finding)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.post(
            f"/v1/review/{_FINDING_ID}/approve",
            json={"justification": "Approved after manual review of the document"},
        )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 409, resp.text
        assert "escalated" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_approve_requires_reviewer_role(self, viewer_client: AsyncClient) -> None:
        """POST /v1/review/{id}/approve with viewer role returns 403."""
        resp = await viewer_client.post(
            f"/v1/review/{_FINDING_ID}/approve",
            json={"justification": "Approved after manual review of the document"},
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_approve_requires_justification(self, reviewer_client: AsyncClient) -> None:
        """POST /v1/review/{id}/approve without justification returns 422."""
        resp = await reviewer_client.post(
            f"/v1/review/{_FINDING_ID}/approve",
            json={},
        )
        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Tests — POST /v1/review/{finding_id}/reject
# ---------------------------------------------------------------------------


class TestRejectFinding:
    @pytest.mark.asyncio
    async def test_reject_sets_status_rejected(self, reviewer_client: AsyncClient) -> None:
        """POST /v1/review/{id}/reject marks operation as rejected."""
        finding = _make_mock_finding(operation_status="escalated")
        session = _make_db_for_load_finding(finding)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        # F7-5: isolate endpoint logic from write-time sealing (covered in
        # tests/api/test_evidence.py).
        with patch(
            "core.chain.seal_operation_with_settings",
            new_callable=AsyncMock,
            return_value={"chain_hash": "x" * 64, "signed": False, "key_version": None},
        ):
            resp = await reviewer_client.post(
                f"/v1/review/{_FINDING_ID}/reject",
                json={"justification": "Rejected: contains real PII, cannot proceed"},
            )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["trace_id"] == str(_TRACE_ID)

        assert finding.operation.status == "rejected"
        assert finding.operation.completed_at is not None

    @pytest.mark.asyncio
    async def test_reject_finding_not_found_returns_404(
        self, reviewer_client: AsyncClient
    ) -> None:
        """POST /v1/review/{id}/reject with unknown finding_id returns 404."""
        session = _make_db_for_load_finding(finding=None)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.post(
            f"/v1/review/{uuid.uuid4()}/reject",
            json={"justification": "Rejected: contains real PII, cannot proceed"},
        )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_reject_non_escalated_returns_409(
        self, reviewer_client: AsyncClient
    ) -> None:
        """POST /v1/review/{id}/reject on non-escalated operation returns 409."""
        finding = _make_mock_finding(operation_status="completed")
        session = _make_db_for_load_finding(finding)

        async def _db() -> AsyncGenerator[Any, None]:
            yield session

        from db.session import get_db as real_get_db

        app.dependency_overrides[real_get_db] = _db
        resp = await reviewer_client.post(
            f"/v1/review/{_FINDING_ID}/reject",
            json={"justification": "Rejected: contains real PII, cannot proceed"},
        )
        app.dependency_overrides.pop(real_get_db, None)

        assert resp.status_code == 409, resp.text

    @pytest.mark.asyncio
    async def test_reject_requires_reviewer_role(self, viewer_client: AsyncClient) -> None:
        """POST /v1/review/{id}/reject with viewer role returns 403."""
        resp = await viewer_client.post(
            f"/v1/review/{_FINDING_ID}/reject",
            json={"justification": "Rejected: contains real PII, cannot proceed"},
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_reject_requires_justification(self, reviewer_client: AsyncClient) -> None:
        """POST /v1/review/{id}/reject without justification returns 422."""
        resp = await reviewer_client.post(
            f"/v1/review/{_FINDING_ID}/reject",
            json={},
        )
        assert resp.status_code == 422, resp.text
