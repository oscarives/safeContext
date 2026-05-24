"""Tests for GDPR retention admin endpoints.

POST /v1/admin/tenants/{tenant_id}/purge
GET  /v1/admin/tenants/{tenant_id}/certificates
GET  /v1/admin/tenants/{tenant_id}/certificates/{cert_id}

All DB and WORM interactions are mocked.
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
    "realm_access": {"roles": ["platform_admin"]},
    "amr": ["otp"],
}

_REVIEWER_PAYLOAD = {
    "sub": "33333333-3333-3333-3333-333333333333",
    "preferred_username": "reviewer",
    "realm_access": {"roles": ["reviewer"]},
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
        "name": "Retention Tenant",
        "slug": "retention-tenant",
        "plan": "enterprise",
        "is_active": True,
        "contact_email": None,
        "max_scans_per_day": None,
        "max_document_size": None,
        "max_storage_mb": None,
        "rate_limit_rpm": None,
        "policy_config": {},
        "siem_config": {},
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
    mock_session.commit = AsyncMock()

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


# ── Purge tests ──────────────────────────────────────────────────────────────


class TestPurgeEndpoint:
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
                resp = await ac.post(f"/v1/admin/tenants/{uuid.uuid4()}/purge")
            app.dependency_overrides.clear()

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_not_found(self, admin_client: AsyncClient):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.post(f"/v1/admin/tenants/{uuid.uuid4()}/purge")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_purge_nothing_to_delete(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch(
            "api.v1.admin_retention.run_gdpr_purge",
            AsyncMock(return_value={
                "purged": False,
                "operations_deleted": 0,
                "certificate_id": None,
            }),
        ):
            resp = await admin_client.post(f"/v1/admin/tenants/{tenant.id}/purge")

        assert resp.status_code == 200
        data = resp.json()
        assert data["purged"] is False
        assert data["operations_deleted"] == 0

    @pytest.mark.asyncio
    async def test_purge_success(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch(
            "api.v1.admin_retention.run_gdpr_purge",
            AsyncMock(return_value={
                "purged": True,
                "operations_deleted": 5,
                "findings_deleted": 12,
                "redactions_deleted": 3,
                "artifacts_deleted": 5,
                "certificate_id": "cert-abc",
                "certificate_stored": True,
                "certificate": {"certificate_type": "gdpr_deletion"},
            }),
        ):
            resp = await admin_client.post(f"/v1/admin/tenants/{tenant.id}/purge")

        assert resp.status_code == 200
        data = resp.json()
        assert data["purged"] is True
        assert data["operations_deleted"] == 5
        assert data["certificate_id"] == "cert-abc"
        assert data["certificate_stored"] is True


# ── Certificates tests ───────────────────────────────────────────────────────


class TestCertificatesEndpoint:
    @pytest.mark.asyncio
    async def test_list_requires_reader_role(self):
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
                resp = await ac.get(f"/v1/admin/tenants/{uuid.uuid4()}/certificates")
            app.dependency_overrides.clear()

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reviewer_can_list_certificates(self):
        tenant = _make_mock_tenant()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def _fake_get_db():
            yield mock_session

        from db.session import get_db as real_get_db

        with (
            patch("core.auth_oidc._decode_token", AsyncMock(return_value=_REVIEWER_PAYLOAD)),
            patch("core.worm._get_minio_client", return_value=None),
        ):
            app.dependency_overrides[real_get_db] = _fake_get_db
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer fake-reviewer-jwt"},
            ) as ac:
                resp = await ac.get(f"/v1/admin/tenants/{tenant.id}/certificates")
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_certificates_tenant_not_found(self, admin_client: AsyncClient):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        resp = await admin_client.get(f"/v1/admin/tenants/{uuid.uuid4()}/certificates")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_certificate_not_found(self, admin_client: AsyncClient):
        tenant = _make_mock_tenant()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

        with patch("core.worm._get_minio_client") as mock_minio:
            mock_client = MagicMock()
            mock_client.get_object.side_effect = Exception("NoSuchKey")
            mock_minio.return_value = mock_client

            resp = await admin_client.get(
                f"/v1/admin/tenants/{tenant.id}/certificates/nonexistent"
            )

        assert resp.status_code == 404
