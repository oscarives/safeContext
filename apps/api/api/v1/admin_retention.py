"""GDPR retention administration endpoints.

POST /v1/admin/tenants/{tenant_id}/purge               — trigger manual purge
GET  /v1/admin/tenants/{tenant_id}/certificates         — list deletion certificates
GET  /v1/admin/tenants/{tenant_id}/certificates/{cert}  — get specific certificate
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import get_roles, require_auth
from core.retention_gdpr import run_gdpr_purge
from db.models.tenant import Tenant
from db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_ADMIN_ROLE = "admin"
_READ_ROLES = ("admin", "reviewer")


def _require_admin(payload: dict) -> None:
    """Raise 403 if the caller does not have the admin role."""
    roles = get_roles(payload)
    if _ADMIN_ROLE not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


def _require_reader(payload: dict) -> None:
    """Raise 403 if the caller lacks read access to retention data."""
    roles = get_roles(payload)
    if not any(r in roles for r in _READ_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin or reviewer role required",
        )


# ── Response schemas ─────────────────────────────────────────────────────────


class PurgeResponse(BaseModel):
    purged: bool
    operations_deleted: int
    findings_deleted: int = 0
    redactions_deleted: int = 0
    artifacts_deleted: int = 0
    certificate_id: str | None = None
    certificate_stored: bool = False
    certificate: dict | None = None


class CertificateSummary(BaseModel):
    certificate_id: str
    object_name: str
    size: int
    last_modified: str | None = None


class CertificateDetail(BaseModel):
    certificate_id: str
    data: dict


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{tenant_id}/purge", response_model=PurgeResponse)
async def trigger_purge(
    tenant_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> PurgeResponse:
    """Trigger a manual GDPR purge for a tenant.

    Deletes operations older than the tenant's configured retention_days.
    Produces a signed deletion certificate stored in WORM.
    Requires admin role.
    """
    _require_admin(auth_payload)

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    retention_days = tenant.retention_days or 365

    log.info(
        "retention.admin.purge_triggered",
        tenant_id=str(tenant_id),
        retention_days=retention_days,
        triggered_by=auth_payload.get("sub"),
    )

    purge_result = await run_gdpr_purge(db, tenant_id, retention_days=retention_days)

    return PurgeResponse(
        purged=purge_result.get("purged", False),
        operations_deleted=purge_result.get("operations_deleted", 0),
        findings_deleted=purge_result.get("findings_deleted", 0),
        redactions_deleted=purge_result.get("redactions_deleted", 0),
        artifacts_deleted=purge_result.get("artifacts_deleted", 0),
        certificate_id=purge_result.get("certificate_id"),
        certificate_stored=purge_result.get("certificate_stored", False),
        certificate=purge_result.get("certificate"),
    )


@router.get("/{tenant_id}/certificates", response_model=list[CertificateSummary])
async def list_certificates(
    tenant_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> list[CertificateSummary]:
    """List deletion certificates for a tenant from WORM storage.

    Requires admin or reviewer role.
    """
    _require_reader(auth_payload)

    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        from core.worm import AUDIT_EVIDENCE_BUCKET, _get_minio_client

        client = _get_minio_client()
        if client is None:
            return []

        prefix = f"{tenant_id}/deletion-certificates/"
        objects = client.list_objects(AUDIT_EVIDENCE_BUCKET, prefix=prefix)

        certs: list[CertificateSummary] = []
        for obj in objects:
            cert_id = obj.object_name.split("/")[-1].replace(".json", "")
            certs.append(
                CertificateSummary(
                    certificate_id=cert_id,
                    object_name=obj.object_name,
                    size=obj.size or 0,
                    last_modified=obj.last_modified.isoformat() if obj.last_modified else None,
                )
            )
        return certs

    except Exception as exc:
        log.warning("retention.list_certificates_failed", error=str(exc))
        return []


@router.get("/{tenant_id}/certificates/{cert_id}", response_model=CertificateDetail)
async def get_certificate(
    tenant_id: uuid.UUID,
    cert_id: str,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> CertificateDetail:
    """Retrieve a specific deletion certificate from WORM storage.

    Requires admin or reviewer role.
    """
    _require_reader(auth_payload)

    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        from core.worm import AUDIT_EVIDENCE_BUCKET, _get_minio_client

        client = _get_minio_client()
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WORM storage unavailable",
            )

        object_name = f"{tenant_id}/deletion-certificates/{cert_id}.json"
        response = client.get_object(AUDIT_EVIDENCE_BUCKET, object_name)
        data = json.loads(response.read())
        response.close()
        response.release_conn()

        return CertificateDetail(certificate_id=cert_id, data=data)

    except HTTPException:
        raise
    except Exception as exc:
        log.warning("retention.get_certificate_failed", cert_id=cert_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate {cert_id} not found",
        ) from exc
