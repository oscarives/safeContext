"""SIEM administration endpoints.

POST /v1/admin/tenants/{tenant_id}/siem/test — send a test event to verify connectivity
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import get_roles, require_auth
from core.siem import SIEMConfig, SIEMEvent, emit_siem_event
from db.models.tenant import Tenant
from db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_ADMIN_ROLE = "admin"


def _require_admin(payload: dict) -> None:
    """Raise 403 if the caller does not have the admin role."""
    roles = get_roles(payload)
    if _ADMIN_ROLE not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


class SIEMTestResponse(BaseModel):
    webhook: bool
    syslog: bool


@router.post(
    "/{tenant_id}/siem/test",
    response_model=SIEMTestResponse,
)
async def test_siem_config(
    tenant_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> SIEMTestResponse:
    """Send a test event to the tenant's configured SIEM destinations.

    Requires admin role.
    """
    _require_admin(auth_payload)

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    raw_config = tenant.siem_config or {}
    config = SIEMConfig(
        enabled=raw_config.get("enabled", False),
        format=raw_config.get("format", "cef"),
        webhook_url=raw_config.get("webhook_url"),
        webhook_token=raw_config.get("webhook_token"),
        syslog_host=raw_config.get("syslog_host"),
        syslog_port=raw_config.get("syslog_port", 514),
        syslog_protocol=raw_config.get("syslog_protocol", "udp"),
    )

    test_event = SIEMEvent(
        event_type="siem.test",
        severity=1,
        trace_id=f"test-{uuid.uuid4()}",
        actor_id=auth_payload.get("sub", "unknown"),
        tenant_id=str(tenant_id),
        details={"message": "SafeContext SIEM connectivity test"},
    )

    delivery = await emit_siem_event(test_event, config)

    log.info(
        "siem.test_sent",
        tenant_id=str(tenant_id),
        webhook=delivery.get("webhook", False),
        syslog=delivery.get("syslog", False),
        tested_by=auth_payload.get("sub"),
    )

    return SIEMTestResponse(
        webhook=delivery.get("webhook", False),
        syslog=delivery.get("syslog", False),
    )
