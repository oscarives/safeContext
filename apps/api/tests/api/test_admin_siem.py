"""Tests for SIEM test endpoint.

POST /v1/admin/tenants/{tenant_id}/siem/test
All external calls are mocked.
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
        "name": "SIEM Tenant",
        "slug": "siem-tenant",
        "plan": "enterprise",
        "is_active": True,
        "contact_email": None,
        "max_scans_per_day": None,
        "max_document_size": None,
        "max_storage_mb": None,
        "rate_limit_rpm": None,
        "policy_config": {},
        "siem_config": {
            "enabled": True,
            "format": "cef",
            "webhook_url": "https://siem.test/events",
            "webhook_token": "secret",
            "syslog_host": None,
            "syslog_port": 514,
            "syslog_protocol": "udp",
        },
        "retention_days": 365,
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


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSIEMTestEndpoint:
    @pytest.mark.asyncio
    async def test_requires_admin(self):
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
                resp = await ac.post(f"/v1/admin/tenants/{uuid.uuid4()}/siem/test")
            app.dependency_overrides.clear()

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_not_found(self, admin_client: AsyncClient):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.post(f"/v1/admin/tenants/{uuid.uuid4()}/siem/test")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_siem_test_success(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch(
            "api.v1.admin_siem.emit_siem_event",
            AsyncMock(return_value={"webhook": True, "syslog": False}),
        ):
            resp = await admin_client.post(f"/v1/admin/tenants/{tenant.id}/siem/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["webhook"] is True
        assert data["syslog"] is False

    @pytest.mark.asyncio
    async def test_siem_disabled(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant(siem_config={"enabled": False})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch(
            "api.v1.admin_siem.emit_siem_event",
            AsyncMock(return_value={"webhook": False, "syslog": False}),
        ):
            resp = await admin_client.post(f"/v1/admin/tenants/{tenant.id}/siem/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["webhook"] is False
        assert data["syslog"] is False

    @pytest.mark.asyncio
    async def test_siem_no_config(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant(siem_config=None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch(
            "api.v1.admin_siem.emit_siem_event",
            AsyncMock(return_value={"webhook": False, "syslog": False}),
        ):
            resp = await admin_client.post(f"/v1/admin/tenants/{tenant.id}/siem/test")

        assert resp.status_code == 200
