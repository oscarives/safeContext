"""GDPR-compliant retention and purge with signed deletion certificates.

Extends the basic retention job (api/v1/retention.py) with:
- Per-tenant retention policy configuration
- Signed deletion certificates (HMAC-SHA256)
- WORM storage of certificates for 7-year compliance
- Detailed audit logging of every deletion

Usage (from scheduler or management command):

    from core.retention_gdpr import run_gdpr_purge

    async with AsyncSessionLocal() as db:
        result = await run_gdpr_purge(db, tenant_id)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.logging import get_logger
from db.models.operation import Operation

logger = get_logger(__name__)

# Default retention: 365 days for operations, configurable per tenant
DEFAULT_RETENTION_DAYS = 365


class DeletionCertificate:
    """Signed certificate proving data was deleted at a specific time.

    Contains enough metadata to satisfy GDPR Art. 17 (right to erasure)
    and Art. 5(2) (accountability principle) requirements.
    """

    def __init__(
        self,
        certificate_id: str,
        tenant_id: str,
        deleted_at: str,
        retention_days: int,
        cutoff_date: str,
        operations_deleted: int,
        operation_ids: list[str],
        findings_deleted: int,
        redactions_deleted: int,
        artifacts_deleted: int,
        deletion_reason: str,
        executor: str,
    ):
        self.certificate_id = certificate_id
        self.tenant_id = tenant_id
        self.deleted_at = deleted_at
        self.retention_days = retention_days
        self.cutoff_date = cutoff_date
        self.operations_deleted = operations_deleted
        self.operation_ids = operation_ids
        self.findings_deleted = findings_deleted
        self.redactions_deleted = redactions_deleted
        self.artifacts_deleted = artifacts_deleted
        self.deletion_reason = deletion_reason
        self.executor = executor
        self.signature: str | None = None

    def to_dict(self) -> dict:
        return {
            "certificate_id": self.certificate_id,
            "certificate_type": "gdpr_deletion",
            "tenant_id": self.tenant_id,
            "deleted_at": self.deleted_at,
            "retention_policy": {
                "retention_days": self.retention_days,
                "cutoff_date": self.cutoff_date,
            },
            "deleted_records": {
                "operations": self.operations_deleted,
                "operation_ids": self.operation_ids,
                "findings": self.findings_deleted,
                "redactions": self.redactions_deleted,
                "artifacts": self.artifacts_deleted,
            },
            "deletion_reason": self.deletion_reason,
            "executor": self.executor,
            "signature": self.signature,
        }

    def sign(self, secret: str) -> str:
        """Sign the certificate with HMAC-SHA256."""
        payload = self.to_dict()
        payload.pop("signature", None)
        data = json.dumps(payload, sort_keys=True, default=str).encode()
        self.signature = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
        return self.signature


async def find_expired_operations(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[Operation]:
    """Find operations older than retention_days for the given tenant.

    Returns the Operation objects (with IDs) so the caller can generate
    a deletion certificate before actually deleting.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    stmt = (
        select(Operation)
        .where(
            Operation.tenant_id == tenant_id,
            Operation.created_at < cutoff,
        )
        .order_by(Operation.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_operations(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    cutoff: datetime,
) -> dict[str, int]:
    """Delete expired operations and return counts.

    CASCADE deletes handle findings, redactions, and artifacts.
    Returns counts of deleted rows for the certificate.
    """
    # Count child records first (before CASCADE removes them)
    from db.models.finding import Finding
    from db.models.redaction import Redaction
    from db.models.artifact import Artifact

    # Subquery for expired operation IDs
    expired_op_ids = (
        select(Operation.id)
        .where(
            Operation.tenant_id == tenant_id,
            Operation.created_at < cutoff,
        )
    )

    findings_count = await db.execute(
        select(func.count(Finding.id)).where(Finding.operation_id.in_(expired_op_ids))
    )
    n_findings = findings_count.scalar() or 0

    redactions_count = await db.execute(
        select(func.count(Redaction.id)).where(Redaction.operation_id.in_(expired_op_ids))
    )
    n_redactions = redactions_count.scalar() or 0

    artifacts_count = await db.execute(
        select(func.count(Artifact.id)).where(Artifact.operation_id.in_(expired_op_ids))
    )
    n_artifacts = artifacts_count.scalar() or 0

    # Delete operations (CASCADE removes children)
    ops_result = await db.execute(
        delete(Operation).where(
            Operation.tenant_id == tenant_id,
            Operation.created_at < cutoff,
        )
    )
    n_ops: int = ops_result.rowcount  # type: ignore[assignment]

    return {
        "operations": n_ops,
        "findings": n_findings,
        "redactions": n_redactions,
        "artifacts": n_artifacts,
    }


def generate_deletion_certificate(
    tenant_id: uuid.UUID,
    retention_days: int,
    cutoff: datetime,
    expired_ops: list[Operation],
    counts: dict[str, int],
    executor: str = "retention-purge-job",
) -> DeletionCertificate:
    """Generate a signed deletion certificate.

    The certificate is signed with HMAC-SHA256 using the API secret key,
    providing non-repudiation of the deletion action.
    """
    now = datetime.now(UTC)

    cert = DeletionCertificate(
        certificate_id=str(uuid.uuid4()),
        tenant_id=str(tenant_id),
        deleted_at=now.isoformat(),
        retention_days=retention_days,
        cutoff_date=cutoff.isoformat(),
        operations_deleted=counts["operations"],
        operation_ids=[str(op.id) for op in expired_ops],
        findings_deleted=counts["findings"],
        redactions_deleted=counts["redactions"],
        artifacts_deleted=counts["artifacts"],
        deletion_reason=f"GDPR retention policy: {retention_days} days",
        executor=executor,
    )

    cert.sign(settings.api_secret_key)
    return cert


async def store_deletion_certificate(cert: DeletionCertificate) -> bool:
    """Store the deletion certificate in WORM storage.

    Falls back gracefully if MinIO is unavailable.
    """
    try:
        from core.worm import store_with_retention

        cert_data = json.dumps(cert.to_dict(), indent=2, default=str).encode()
        object_name = f"{cert.tenant_id}/deletion-certificates/{cert.certificate_id}.json"

        return store_with_retention(
            object_name=object_name,
            data=cert_data,
            content_type="application/json",
            retention_days=2555,  # 7 years
            metadata={
                "certificate_type": "gdpr_deletion",
                "tenant_id": cert.tenant_id,
            },
        )
    except Exception as exc:
        logger.warning(
            "retention.certificate_store_failed",
            certificate_id=cert.certificate_id,
            error=str(exc),
        )
        return False


async def run_gdpr_purge(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    executor: str = "retention-purge-job",
) -> dict:
    """Execute GDPR-compliant data purge for a tenant.

    Steps:
    1. Find expired operations
    2. Count child records
    3. Delete operations (CASCADE)
    4. Generate signed deletion certificate
    5. Store certificate in WORM storage
    6. Return summary

    Returns a dict with purge results and certificate metadata.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    logger.info(
        "retention.gdpr_purge.start",
        tenant_id=str(tenant_id),
        retention_days=retention_days,
        cutoff=cutoff.isoformat(),
        executor=executor,
    )

    # Step 1: Find expired operations (for certificate)
    expired_ops = await find_expired_operations(db, tenant_id, retention_days)

    if not expired_ops:
        logger.info(
            "retention.gdpr_purge.nothing_to_purge",
            tenant_id=str(tenant_id),
        )
        return {
            "purged": False,
            "operations_deleted": 0,
            "certificate_id": None,
        }

    # Step 2-3: Delete and count
    counts = await delete_operations(db, tenant_id, cutoff)
    await db.commit()

    # Step 4: Generate signed certificate
    cert = generate_deletion_certificate(
        tenant_id=tenant_id,
        retention_days=retention_days,
        cutoff=cutoff,
        expired_ops=expired_ops,
        counts=counts,
        executor=executor,
    )

    # Step 5: Store in WORM
    stored = await store_deletion_certificate(cert)

    logger.info(
        "retention.gdpr_purge.complete",
        tenant_id=str(tenant_id),
        operations_deleted=counts["operations"],
        findings_deleted=counts["findings"],
        certificate_id=cert.certificate_id,
        certificate_stored=stored,
    )

    return {
        "purged": True,
        "operations_deleted": counts["operations"],
        "findings_deleted": counts["findings"],
        "redactions_deleted": counts["redactions"],
        "artifacts_deleted": counts["artifacts"],
        "certificate_id": cert.certificate_id,
        "certificate_stored": stored,
        "certificate": cert.to_dict(),
    }
