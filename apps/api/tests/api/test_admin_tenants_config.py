"""Tests for tenant configuration fields (policy_config, siem_config, retention_days).

Extends the existing admin_tenants API with per-tenant configuration validation.
All DB interactions are mocked.
"""
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
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
}

_USER_PAYLOAD = {
    "sub": "22222222-2222-2222-2222-222222222222",
    "preferred_username": "user",
    "realm_access": {"roles": ["viewer"]},
    "amr": ["otp"],
}


def _make_mock_tenant(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "name": "Config Tenant",
        "slug": "config-tenant",
        "plan": "enterprise",
        "is_active": True,
        "contact_email": "admin@test.com",
        "max_scans_per_day": 1000,
        "max_document_size": None,
        "max_storage_mb": None,
        "rate_limit_rpm": None,
        "policy_config": {
            "confidence_overrides": {"API_KEY": 0.80},
            "severity_overrides": {"IP_ADDRESS": "high"},
            "blocked_entity_types": ["SSN"],
        },
        "siem_config": {
            "enabled": True,
            "format": "cef",
            "webhook_url": "https://siem.test/events",
            "webhook_token": None,
            "syslog_host": None,
            "syslog_port": 514,
            "syslog_protocol": "udp",
        },
        "retention_days": 90,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    tenant = MagicMock()
    for k, v in defaults.items():
        setattr(tenant, k, v)
    return tenant


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[AsyncClient, None]:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

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


# ── Tests: policy_config ─────────────────────────────────────────────────────


class TestPolicyConfig:
    @pytest.mark.asyncio
    async def test_create_tenant_with_policy_config(self, admin_client: AsyncClient):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        async def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            obj.is_active = True
            obj.policy_config = {"confidence_overrides": {"API_KEY": 0.80}, "severity_overrides": {}, "blocked_entity_types": []}
            obj.siem_config = None
            obj.retention_days = None

        admin_client._mock_session.refresh = AsyncMock(side_effect=_refresh)  # type: ignore[attr-defined]

        resp = await admin_client.post(
            "/v1/admin/tenants",
            json={
                "name": "Policy Tenant",
                "slug": "policy-tenant",
                "policy_config": {
                    "confidence_overrides": {"API_KEY": 0.80},
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["policy_config"]["confidence_overrides"]["API_KEY"] == 0.80

    @pytest.mark.asyncio
    async def test_update_policy_config(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]
        admin_client._mock_session.refresh = AsyncMock()  # type: ignore[attr-defined]

        resp = await admin_client.patch(
            f"/v1/admin/tenants/{tenant.id}",
            json={
                "policy_config": {
                    "confidence_overrides": {"EMAIL_ADDRESS": 0.90},
                    "severity_overrides": {"IP_ADDRESS": "critical"},
                    "blocked_entity_types": ["CREDIT_CARD", "SSN"],
                },
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_confidence_value(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.patch(
            f"/v1/admin/tenants/{tenant.id}",
            json={
                "policy_config": {
                    "confidence_overrides": {"API_KEY": 1.5},
                },
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_entity_type(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.patch(
            f"/v1/admin/tenants/{tenant.id}",
            json={
                "policy_config": {
                    "confidence_overrides": {"UNKNOWN_TYPE": 0.5},
                },
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_severity_value(self, admin_client: AsyncClient):
        resp = await admin_client.patch(
            f"/v1/admin/tenants/{uuid.uuid4()}",
            json={
                "policy_config": {
                    "severity_overrides": {"API_KEY": "extreme"},
                },
            },
        )
        assert resp.status_code == 422


# ── Tests: siem_config ───────────────────────────────────────────────────────


class TestSIEMConfig:
    @pytest.mark.asyncio
    async def test_update_siem_config(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]
        admin_client._mock_session.refresh = AsyncMock()  # type: ignore[attr-defined]

        resp = await admin_client.patch(
            f"/v1/admin/tenants/{tenant.id}",
            json={
                "siem_config": {
                    "enabled": True,
                    "format": "leef",
                    "webhook_url": "https://siem.corp/events",
                    "syslog_host": "10.0.1.100",
                    "syslog_port": 1514,
                    "syslog_protocol": "tcp",
                },
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_siem_format(self, admin_client: AsyncClient):
        resp = await admin_client.patch(
            f"/v1/admin/tenants/{uuid.uuid4()}",
            json={
                "siem_config": {
                    "format": "xml",
                },
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_syslog_port(self, admin_client: AsyncClient):
        resp = await admin_client.patch(
            f"/v1/admin/tenants/{uuid.uuid4()}",
            json={
                "siem_config": {
                    "syslog_port": 99999,
                },
            },
        )
        assert resp.status_code == 422


# ── Tests: retention_days ────────────────────────────────────────────────────


class TestRetentionDays:
    @pytest.mark.asyncio
    async def test_update_retention_days(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]
        admin_client._mock_session.refresh = AsyncMock()  # type: ignore[attr-defined]

        resp = await admin_client.patch(
            f"/v1/admin/tenants/{tenant.id}",
            json={"retention_days": 30},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_negative_retention_days_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.patch(
            f"/v1/admin/tenants/{uuid.uuid4()}",
            json={"retention_days": -1},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_excessive_retention_days_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.patch(
            f"/v1/admin/tenants/{uuid.uuid4()}",
            json={"retention_days": 5000},
        )
        assert resp.status_code == 422


# ── Tests: response includes new fields ──────────────────────────────────────


class TestResponseIncludes:
    @pytest.mark.asyncio
    async def test_get_tenant_includes_config_fields(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.get(f"/v1/admin/tenants/{tenant.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "policy_config" in data
        assert "siem_config" in data
        assert "retention_days" in data
        assert data["retention_days"] == 90
        assert data["policy_config"]["blocked_entity_types"] == ["SSN"]

    @pytest.mark.asyncio
    async def test_list_tenants_includes_config_fields(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [tenant]
        mock_result.scalars.return_value = mock_scalars
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.get("/v1/admin/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "policy_config" in data[0]
        assert data[0]["siem_config"]["enabled"] is True
