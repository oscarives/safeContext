"""Tenant quota enforcement for SafeContext API (F6-A4).

Provides middleware to check and enforce tenant-level quotas:
- max_scans_per_day: daily scan operations limit
- max_document_size: maximum document size in bytes
- rate_limit_rpm: requests per minute per tenant

Quota counters are stored in Redis with TTL-based daily expiry.
Falls back to in-memory counters when Redis is unavailable.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict

import structlog
from fastapi import HTTPException, Request, status

from core.constants import DEFAULT_TENANT_ID

log = structlog.get_logger(__name__)

# In-memory fallback counters (for when Redis is unavailable)
_daily_scan_counts: dict[str, int] = defaultdict(int)
_daily_scan_day: str = ""  # YYYY-MM-DD to detect day rollover
_rpm_timestamps: dict[str, list[float]] = defaultdict(list)


def _today_key() -> str:
    """Return today's date string for daily counter keys."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _get_daily_scan_count_redis(
    tenant_id: uuid.UUID,
    redis_client: object | None,
) -> int | None:
    """Get current daily scan count from Redis. Returns None if Redis unavailable."""
    if redis_client is None:
        return None
    try:
        key = f"quota:scans:{tenant_id}:{_today_key()}"
        val = await redis_client.get(key)  # type: ignore[union-attr]
        return int(val) if val is not None else 0
    except Exception:
        log.warning("quotas.redis_get_failed", tenant_id=str(tenant_id))
        return None


async def _increment_daily_scan_count_redis(
    tenant_id: uuid.UUID,
    redis_client: object | None,
) -> int | None:
    """Increment daily scan count in Redis. Returns new count or None if unavailable."""
    if redis_client is None:
        return None
    try:
        key = f"quota:scans:{tenant_id}:{_today_key()}"
        pipe = redis_client.pipeline(transaction=True)  # type: ignore[union-attr]
        pipe.incr(key)
        pipe.expire(key, 86400 + 3600)  # 25h TTL for safety
        results = await pipe.execute()
        return int(results[0])
    except Exception:
        log.warning("quotas.redis_incr_failed", tenant_id=str(tenant_id))
        return None


def _get_daily_scan_count_memory(tenant_id: uuid.UUID) -> int:
    """Get/manage daily scan count using in-memory fallback."""
    global _daily_scan_day
    today = _today_key()
    if _daily_scan_day != today:
        _daily_scan_counts.clear()
        _daily_scan_day = today
    return _daily_scan_counts[str(tenant_id)]


def _increment_daily_scan_count_memory(tenant_id: uuid.UUID) -> int:
    """Increment daily scan count in memory. Returns new count."""
    global _daily_scan_day
    today = _today_key()
    if _daily_scan_day != today:
        _daily_scan_counts.clear()
        _daily_scan_day = today
    key = str(tenant_id)
    _daily_scan_counts[key] += 1
    return _daily_scan_counts[key]


def check_document_size(document: str, max_document_size: int | None) -> None:
    """Raise 413 if document exceeds tenant's max_document_size limit."""
    if max_document_size is None:
        return  # unlimited
    doc_bytes = len(document.encode("utf-8"))
    if doc_bytes > max_document_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Document size ({doc_bytes} bytes) exceeds tenant limit "
                f"({max_document_size} bytes)"
            ),
        )


async def check_daily_scan_quota(
    tenant_id: uuid.UUID,
    max_scans_per_day: int | None,
    request: Request,
) -> None:
    """Raise 429 if tenant has exceeded daily scan quota."""
    if max_scans_per_day is None:
        return  # unlimited

    redis_client = getattr(request.app.state, "redis_rl", None)
    count = await _get_daily_scan_count_redis(tenant_id, redis_client)
    if count is None:
        count = _get_daily_scan_count_memory(tenant_id)

    if count >= max_scans_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily scan quota exceeded ({max_scans_per_day} scans/day)",
            headers={"Retry-After": "3600"},
        )


async def increment_scan_count(
    tenant_id: uuid.UUID,
    request: Request,
) -> None:
    """Increment the daily scan counter after a successful scan enqueue."""
    redis_client = getattr(request.app.state, "redis_rl", None)
    result = await _increment_daily_scan_count_redis(tenant_id, redis_client)
    if result is None:
        _increment_daily_scan_count_memory(tenant_id)


def check_tenant_rate_limit(
    tenant_id: uuid.UUID,
    rate_limit_rpm: int | None,
) -> None:
    """Simple in-memory per-tenant RPM rate limiter. Raise 429 if exceeded."""
    if rate_limit_rpm is None:
        return  # unlimited

    now = time.monotonic()
    key = str(tenant_id)
    window = _rpm_timestamps[key]

    # Evict timestamps older than 60s
    cutoff = now - 60.0
    _rpm_timestamps[key] = [t for t in window if t > cutoff]

    if len(_rpm_timestamps[key]) >= rate_limit_rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Tenant rate limit exceeded ({rate_limit_rpm} requests/min)",
            headers={"Retry-After": "60"},
        )

    _rpm_timestamps[key].append(now)
