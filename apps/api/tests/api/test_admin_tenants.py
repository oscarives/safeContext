"""Tests for tenant admin API (F6-A5).

Tests CRUD operations on /v1/admin/tenants endpoints.
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

_ADMIN_SUB = "11111111-1111-1111-1111-111111111111"
_NON_ADMIN_SUB = "22222222-2222-2222-2222-222222222222"

_ADMIN_PAYLOAD = {
    "sub": _ADMIN_SUB,
    "preferred_username": "admin",
    "realm_access": {"roles": ["admin"]},
    "amr": ["otp"],
}

_USER_PAYLOAD = {
    "sub": _NON_ADMIN_SUB,
    "preferred_username": "user",
    "realm_access": {"roles": ["viewer"]},
    "amr": ["otp"],
}


def _make_mock_tenant(**overrides):
    """Create a mock tenant object with sensible defaults."""
    from datetime import datetime, timezone

    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Tenant",
        "slug": "test-tenant",
        "plan": "free",
        "is_active": True,
        "contact_email": "admin@test.com",
        "max_scans_per_day": 100,
        "max_document_size": None,
        "max_storage_mb": None,
        "rate_limit_rpm": None,
        "policy_config": None,
        "siem_config": None,
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
    """Client authenticated as admin."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _fake_get_db() -> AsyncGenerator[Any, None]:
        yield mock_session

    from db.session import get_db as real_get_db

    with patch("core.auth_oidc._decode_token", AsyncMock(return_value=_ADMIN_PAYLOAD)):
        app.dependency_overrides[real_get_db] = _fake_get_db
        # Store mock_session on the client for test access
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-admin-jwt"},
        ) as ac:
            ac._mock_session = mock_session  # type: ignore[attr-defined]
            yield ac
        app.dependency_overrides.clear()


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tenants_requires_admin():
    """Non-admin users get 403."""
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
            resp = await ac.get("/v1/admin/tenants")
        app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_tenants_empty(admin_client: AsyncClient):
    """Admin listing tenants on empty DB returns empty list."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    resp = await admin_client.get("/v1/admin/tenants")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_tenants_returns_data(admin_client: AsyncClient):
    """Admin listing tenants returns tenant data."""
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
    assert data[0]["slug"] == "test-tenant"


@pytest.mark.asyncio
async def test_create_tenant_success(admin_client: AsyncClient):
    """Admin can create a new tenant."""
    # Mock: no existing tenant with same slug
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    # Mock refresh to populate fields
    async def _refresh(obj):
        from datetime import datetime, timezone

        obj.id = uuid.uuid4()
        obj.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        obj.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        obj.is_active = True

    admin_client._mock_session.refresh = AsyncMock(side_effect=_refresh)  # type: ignore[attr-defined]

    resp = await admin_client.post(
        "/v1/admin/tenants",
        json={
            "name": "Acme Corp",
            "slug": "acme-corp",
            "plan": "starter",
            "max_scans_per_day": 500,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert data["plan"] == "starter"
    assert data["max_scans_per_day"] == 500


@pytest.mark.asyncio
async def test_create_tenant_duplicate_slug(admin_client: AsyncClient):
    """Creating a tenant with duplicate slug returns 409."""
    existing = _make_mock_tenant(slug="existing")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    resp = await admin_client.post(
        "/v1/admin/tenants",
        json={"name": "Existing", "slug": "existing"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_tenant_invalid_slug(admin_client: AsyncClient):
    """Invalid slug format returns 422."""
    resp = await admin_client.post(
        "/v1/admin/tenants",
        json={"name": "Bad", "slug": "BAD_SLUG!"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_tenant_not_found(admin_client: AsyncClient):
    """Getting nonexistent tenant returns 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    resp = await admin_client.get(f"/v1/admin/tenants/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_tenant_success(admin_client: AsyncClient):
    """Admin can update tenant settings."""
    tenant = _make_mock_tenant()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tenant
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    async def _refresh(obj):
        pass  # keep current values

    admin_client._mock_session.refresh = AsyncMock(side_effect=_refresh)  # type: ignore[attr-defined]

    resp = await admin_client.patch(
        f"/v1/admin/tenants/{tenant.id}",
        json={"plan": "enterprise", "max_scans_per_day": 10000},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_deactivate_tenant(admin_client: AsyncClient):
    """Admin can deactivate a tenant."""
    tenant = _make_mock_tenant()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tenant
    admin_client._mock_session.execute = AsyncMock(return_value=mock_result)  # type: ignore[attr-defined]

    resp = await admin_client.delete(f"/v1/admin/tenants/{tenant.id}")
    assert resp.status_code == 204
    assert tenant.is_active is False
