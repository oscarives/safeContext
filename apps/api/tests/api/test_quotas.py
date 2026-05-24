"""Tests for tenant quota enforcement (F6-A4)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.quotas import (
    check_daily_scan_quota,
    check_document_size,
    check_tenant_rate_limit,
    increment_scan_count,
    _daily_scan_counts,
    _rpm_timestamps,
)

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_request(redis_client=None):
    req = MagicMock()
    req.app.state.redis_rl = redis_client
    return req


class TestDocumentSize:
    def test_allows_within_limit(self):
        check_document_size("hello", 1000)  # 5 bytes < 1000

    def test_allows_unlimited(self):
        check_document_size("x" * 10_000_000, None)

    def test_rejects_over_limit(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            check_document_size("x" * 200, 100)
        assert exc_info.value.status_code == 413

    def test_unicode_counts_bytes(self):
        # "é" is 2 bytes in UTF-8
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            check_document_size("é" * 60, 100)  # 120 bytes > 100


class TestDailyScanQuota:
    @pytest.fixture(autouse=True)
    def _clear_counters(self):
        _daily_scan_counts.clear()
        yield
        _daily_scan_counts.clear()

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        req = _make_request()
        await check_daily_scan_quota(TENANT_A, 10, req)  # 0 < 10

    @pytest.mark.asyncio
    async def test_allows_unlimited(self):
        req = _make_request()
        await check_daily_scan_quota(TENANT_A, None, req)

    @pytest.mark.asyncio
    async def test_rejects_over_limit(self):
        from fastapi import HTTPException

        req = _make_request()
        # Manually set counter to the limit
        _daily_scan_counts[str(TENANT_A)] = 5
        with pytest.raises(HTTPException) as exc_info:
            await check_daily_scan_quota(TENANT_A, 5, req)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_tenants_isolated(self):
        req = _make_request()
        _daily_scan_counts[str(TENANT_A)] = 100
        # Tenant B should still be under limit
        await check_daily_scan_quota(TENANT_B, 10, req)

    @pytest.mark.asyncio
    async def test_increment_updates_counter(self):
        req = _make_request()
        assert _daily_scan_counts[str(TENANT_A)] == 0
        await increment_scan_count(TENANT_A, req)
        assert _daily_scan_counts[str(TENANT_A)] == 1
        await increment_scan_count(TENANT_A, req)
        assert _daily_scan_counts[str(TENANT_A)] == 2


class TestTenantRateLimit:
    @pytest.fixture(autouse=True)
    def _clear_timestamps(self):
        _rpm_timestamps.clear()
        yield
        _rpm_timestamps.clear()

    def test_allows_under_limit(self):
        check_tenant_rate_limit(TENANT_A, 100)

    def test_allows_unlimited(self):
        check_tenant_rate_limit(TENANT_A, None)

    def test_rejects_over_limit(self):
        import time
        from fastapi import HTTPException

        # Fill up the window
        key = str(TENANT_A)
        now = time.monotonic()
        _rpm_timestamps[key] = [now] * 5

        with pytest.raises(HTTPException) as exc_info:
            check_tenant_rate_limit(TENANT_A, 5)
        assert exc_info.value.status_code == 429

    def test_tenants_isolated(self):
        import time

        key_a = str(TENANT_A)
        now = time.monotonic()
        _rpm_timestamps[key_a] = [now] * 100
        # Tenant B should still pass
        check_tenant_rate_limit(TENANT_B, 10)
