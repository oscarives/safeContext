"""WORM (Write Once Read Many) retention for audit evidence (F6-B4).

Uses MinIO Object Lock in GOVERNANCE mode to prevent deletion or modification
of audit artifacts until the retention period expires.

Configuration:
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY from settings.
    Default retention: 7 years (2555 days) for financial compliance.
    Configurable per-tenant via Tenant.max_storage_mb (retention days TBD).

The GOVERNANCE mode allows users with s3:BypassGovernanceRetention permission
to override retention in emergency (4-eyes approval process).
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import structlog

from config import settings

log = structlog.get_logger(__name__)

# Default retention period in days (7 years for SOX/financial compliance)
DEFAULT_RETENTION_DAYS = 2555

# Bucket for audit evidence with Object Lock enabled
AUDIT_EVIDENCE_BUCKET = "safecontext-audit-evidence"


def _get_minio_client():
    """Create a MinIO client. Lazy import to avoid hard dependency in tests."""
    try:
        from minio import Minio
        return Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
    except ImportError:
        log.warning("worm.minio_not_installed")
        return None
    except Exception as exc:
        log.warning("worm.minio_client_failed", error=str(exc))
        return None


async def ensure_audit_bucket() -> bool:
    """Ensure the audit evidence bucket exists with Object Lock enabled.

    This is idempotent — safe to call on every startup.
    Object Lock can only be set at bucket creation time.
    Returns True if bucket is ready, False on failure.
    """
    client = _get_minio_client()
    if client is None:
        return False

    try:
        if client.bucket_exists(AUDIT_EVIDENCE_BUCKET):
            return True

        # Create bucket with Object Lock enabled
        client.make_bucket(AUDIT_EVIDENCE_BUCKET, object_lock=True)
        log.info("worm.bucket_created", bucket=AUDIT_EVIDENCE_BUCKET)
        return True

    except Exception as exc:
        log.warning("worm.ensure_bucket_failed", error=str(exc))
        return False


def store_with_retention(
    object_name: str,
    data: bytes,
    content_type: str = "application/json",
    retention_days: int | None = None,
    metadata: dict[str, str] | None = None,
) -> bool:
    """Store an object in the audit evidence bucket with WORM retention.

    Args:
        object_name: Key/path for the object (e.g., "tenant-id/trace-id/audit.json")
        data: Raw bytes to store
        content_type: MIME type
        retention_days: Override retention period (defaults to DEFAULT_RETENTION_DAYS)
        metadata: Optional user metadata dict

    Returns:
        True if stored successfully, False on failure.
    """
    client = _get_minio_client()
    if client is None:
        return False

    days = retention_days or DEFAULT_RETENTION_DAYS
    retain_until = datetime.now(timezone.utc) + timedelta(days=days)

    try:
        from minio.retention import Retention
        from minio.commonconfig import GOVERNANCE

        retention = Retention(GOVERNANCE, retain_until)

        client.put_object(
            AUDIT_EVIDENCE_BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata or {},
            retention=retention,
        )

        log.info(
            "worm.object_stored",
            bucket=AUDIT_EVIDENCE_BUCKET,
            object_name=object_name,
            retention_days=days,
            retain_until=retain_until.isoformat(),
        )
        return True

    except Exception as exc:
        log.warning(
            "worm.store_failed",
            object_name=object_name,
            error=str(exc),
        )
        return False


def check_retention(object_name: str) -> dict | None:
    """Check the retention status of an object.

    Returns dict with mode, retain_until_date, and is_locked fields,
    or None if the object doesn't exist or MinIO is unavailable.
    """
    client = _get_minio_client()
    if client is None:
        return None

    try:
        retention = client.get_object_retention(AUDIT_EVIDENCE_BUCKET, object_name)
        return {
            "mode": str(retention.mode) if retention else "none",
            "retain_until_date": retention.retain_until_date.isoformat() if retention and retention.retain_until_date else None,
            "is_locked": retention is not None,
        }
    except Exception:
        return None


def delete_with_governance_bypass(object_name: str) -> bool:
    """Delete an object by bypassing GOVERNANCE retention (4-eyes emergency).

    This requires the MinIO user to have s3:BypassGovernanceRetention permission.
    Should only be used in exceptional circumstances with documented approval.

    Returns True if deleted, False on failure.
    """
    client = _get_minio_client()
    if client is None:
        return False

    try:
        client.remove_object(
            AUDIT_EVIDENCE_BUCKET,
            object_name,
            bypass_governance_mode=True,
        )
        log.warning(
            "worm.governance_bypass_delete",
            object_name=object_name,
            bucket=AUDIT_EVIDENCE_BUCKET,
        )
        return True
    except Exception as exc:
        log.error("worm.governance_bypass_failed", error=str(exc))
        return False
