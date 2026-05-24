"""Tests for F6-C3 compliance report endpoint and generation logic.

All DB interactions are mocked.
"""
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app

# ── Helpers ──────────────────────────────────────────────────────────────────

_ADMIN_PAYLOAD = {
    "sub": "11111111-1111-1111-1111-111111111111",
    "preferred_username": "admin",
    "realm_access": {"roles": ["admin"]},
    "amr": ["otp"],
    "tenant_id": "00000000-0000-0000-0000-000000000000",
}

_REVIEWER_PAYLOAD = {
    "sub": "22222222-2222-2222-2222-222222222222",
    "preferred_username": "reviewer",
    "realm_access": {"roles": ["reviewer"]},
    "amr": ["otp"],
    "tenant_id": "00000000-0000-0000-0000-000000000000",
}

_USER_PAYLOAD = {
    "sub": "33333333-3333-3333-3333-333333333333",
    "preferred_username": "user",
    "realm_access": {"roles": ["viewer"]},
    "amr": ["otp"],
}


def _mock_scalar(value):
    """Create a mock DB result that returns a scalar value."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    # Mock execute to return scalar results for count queries
    mock_session.execute = AsyncMock(return_value=_mock_scalar(42))

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    from db.session import get_db as real_get_db

    with patch("core.auth_oidc._decode_token", AsyncMock(return_value=_ADMIN_PAYLOAD)):
        app.dependency_overrides[real_get_db] = _fake_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-admin-jwt"},
        ) as ac:
            ac._mock_session = mock_session  # type: ignore[attr-defined]
            yield ac
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def reviewer_client() -> AsyncGenerator[AsyncClient, None]:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=_mock_scalar(10))

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    from db.session import get_db as real_get_db

    with patch("core.auth_oidc._decode_token", AsyncMock(return_value=_REVIEWER_PAYLOAD)):
        app.dependency_overrides[real_get_db] = _fake_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-reviewer-jwt"},
        ) as ac:
            yield ac
        app.dependency_overrides.clear()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestComplianceEndpoint:
    @pytest.mark.asyncio
    async def test_soc2_report(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=soc2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "soc2"
        assert data["framework_version"] == "SOC 2 Type II (2017)"
        assert len(data["controls"]) == 5
        assert "summary" in data
        assert data["summary"]["total_controls"] == 5

    @pytest.mark.asyncio
    async def test_iso27001_report(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=iso27001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "iso27001"
        assert len(data["controls"]) == 5

    @pytest.mark.asyncio
    async def test_gdpr_report(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=gdpr")
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "gdpr"
        assert len(data["controls"]) == 5
        # GDPR Art.30 should be present
        control_ids = [c["control_id"] for c in data["controls"]]
        assert "Art.30" in control_ids

    @pytest.mark.asyncio
    async def test_default_framework_is_soc2(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report")
        assert resp.status_code == 200
        assert resp.json()["framework"] == "soc2"

    @pytest.mark.asyncio
    async def test_custom_period(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?period_days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["period_days"] == 30

    @pytest.mark.asyncio
    async def test_invalid_framework_returns_422(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=pci")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reviewer_can_access(self, reviewer_client: AsyncClient):
        resp = await reviewer_client.get("/v1/admin/compliance/report?framework=soc2")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_denied(self):
        """Regular viewer gets 403."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _fake_get_db():
            yield mock_session

        from db.session import get_db as real_get_db

        with patch("core.auth_oidc._decode_token", AsyncMock(return_value=_USER_PAYLOAD)):
            app.dependency_overrides[real_get_db] = _fake_get_db
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer fake-user-jwt"},
            ) as ac:
                resp = await ac.get("/v1/admin/compliance/report")
            app.dependency_overrides.clear()

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_compliance_score_calculation(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=soc2")
        assert resp.status_code == 200
        data = resp.json()
        summary = data["summary"]
        # Score should be 0.0 - 1.0
        assert 0.0 <= summary["compliance_score"] <= 1.0
        # met + partial + not_met + not_applicable == total
        assert (
            summary["met"] + summary["partial"] + summary["not_met"] + summary["not_applicable"]
            == summary["total_controls"]
        )

    @pytest.mark.asyncio
    async def test_controls_have_evidence(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report?framework=soc2")
        assert resp.status_code == 200
        data = resp.json()
        for control in data["controls"]:
            assert "control_id" in control
            assert "control_name" in control
            assert "status" in control
            assert control["status"] in ("met", "partial", "not_met", "not_applicable")
            assert isinstance(control["evidence"], list)

    @pytest.mark.asyncio
    async def test_report_has_metadata(self, admin_client: AsyncClient):
        resp = await admin_client.get("/v1/admin/compliance/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert "generated_at" in data
        assert "tenant_id" in data
        assert "period_start" in data
        assert "period_end" in data


class TestComplianceGeneration:
    def test_evaluate_control_all_evidence_met(self):
        from api.v1.compliance import _evaluate_control

        template = {
            "control_id": "TEST-1",
            "control_name": "Test Control",
            "description": "test",
            "evidence_keys": ["key1", "key2"],
        }
        evidence = {
            "key1": ["evidence 1"],
            "key2": ["evidence 2"],
        }
        result = _evaluate_control(template, evidence)
        assert result.status == "met"
        assert len(result.evidence) == 2

    def test_evaluate_control_partial_evidence(self):
        from api.v1.compliance import _evaluate_control

        template = {
            "control_id": "TEST-2",
            "control_name": "Partial",
            "description": "test",
            "evidence_keys": ["key1", "key2"],
        }
        evidence = {"key1": ["evidence 1"]}
        result = _evaluate_control(template, evidence)
        assert result.status == "partial"

    def test_evaluate_control_no_evidence(self):
        from api.v1.compliance import _evaluate_control

        template = {
            "control_id": "TEST-3",
            "control_name": "Missing",
            "description": "test",
            "evidence_keys": ["missing1", "missing2"],
        }
        result = _evaluate_control(template, {})
        assert result.status == "not_met"

    def test_framework_templates_exist(self):
        from schemas.compliance import FRAMEWORK_TEMPLATES, FRAMEWORK_VERSIONS

        for fw in ("soc2", "iso27001", "gdpr"):
            assert fw in FRAMEWORK_TEMPLATES
            assert fw in FRAMEWORK_VERSIONS
            assert len(FRAMEWORK_TEMPLATES[fw]) >= 3
