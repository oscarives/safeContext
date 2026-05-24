"""Tenant administration endpoints (F6-A5).

CRUD operations for tenant management, restricted to ``platform_admin`` role.

GET    /v1/admin/tenants              — list all tenants
POST   /v1/admin/tenants              — create a new tenant
GET    /v1/admin/tenants/{tenant_id}  — get tenant details
PATCH  /v1/admin/tenants/{tenant_id}  — update tenant settings
DELETE /v1/admin/tenants/{tenant_id}  — deactivate (soft-delete) a tenant
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import get_roles, require_auth
from db.enums import TenantPlan
from db.models.tenant import Tenant
from db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_ADMIN_ROLE = "platform_admin"


def _require_platform_admin(payload: dict) -> None:
    """Raise 403 if the caller does not have the platform_admin role."""
    roles = get_roles(payload)
    if _ADMIN_ROLE not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="platform_admin role required",
        )


# ── Sub-schemas for per-tenant configuration ────────────────────────────────

_VALID_ENTITY_TYPES = {
    "EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON", "API_KEY", "PASSWORD",
    "CREDIT_CARD", "SSN", "IBAN_CODE", "IP_ADDRESS", "MEDICAL_RECORD",
}
_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


class PolicyConfigSchema(BaseModel):
    """Per-tenant detection policy overrides sent to OPA ``tenant_decision()``."""

    confidence_overrides: dict[str, float] = {}
    severity_overrides: dict[str, str] = {}
    blocked_entity_types: list[str] = []

    @field_validator("confidence_overrides")
    @classmethod
    def validate_confidence_values(cls, v: dict[str, float]) -> dict[str, float]:
        for entity, threshold in v.items():
            if entity not in _VALID_ENTITY_TYPES:
                raise ValueError(f"Unknown entity type: {entity}")
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(f"Confidence for {entity} must be 0.0–1.0, got {threshold}")
        return v

    @field_validator("severity_overrides")
    @classmethod
    def validate_severity_values(cls, v: dict[str, str]) -> dict[str, str]:
        for entity, sev in v.items():
            if entity not in _VALID_ENTITY_TYPES:
                raise ValueError(f"Unknown entity type: {entity}")
            if sev not in _VALID_SEVERITIES:
                raise ValueError(f"Invalid severity for {entity}: {sev}")
        return v

    @field_validator("blocked_entity_types")
    @classmethod
    def validate_blocked_types(cls, v: list[str]) -> list[str]:
        for entity in v:
            if entity not in _VALID_ENTITY_TYPES:
                raise ValueError(f"Unknown entity type: {entity}")
        return v


class SIEMConfigSchema(BaseModel):
    """Per-tenant SIEM integration settings."""

    enabled: bool = False
    format: Literal["cef", "leef", "json"] = "cef"
    webhook_url: str | None = None
    webhook_token: str | None = None
    syslog_host: str | None = None
    syslog_port: int = Field(default=514, ge=1, le=65535)
    syslog_protocol: Literal["udp", "tcp"] = "udp"


# ── Schemas ──────────────────────────────────────────────────────────────────


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    plan: TenantPlan = TenantPlan.FREE
    contact_email: str | None = None
    max_scans_per_day: int | None = None
    max_document_size: int | None = None
    max_storage_mb: int | None = None
    rate_limit_rpm: int | None = None
    policy_config: PolicyConfigSchema | None = None
    siem_config: SIEMConfigSchema | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class TenantUpdate(BaseModel):
    name: str | None = None
    plan: TenantPlan | None = None
    is_active: bool | None = None
    contact_email: str | None = None
    max_scans_per_day: int | None = Field(default=None)
    max_document_size: int | None = Field(default=None)
    max_storage_mb: int | None = Field(default=None)
    rate_limit_rpm: int | None = Field(default=None)
    policy_config: PolicyConfigSchema | None = None
    siem_config: SIEMConfigSchema | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    contact_email: str | None
    max_scans_per_day: int | None
    max_document_size: int | None
    max_storage_mb: int | None
    rate_limit_rpm: int | None
    policy_config: dict | None = None
    siem_config: dict | None = None
    retention_days: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    """List all tenants. Requires platform_admin role."""
    _require_platform_admin(auth_payload)

    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()
    return [TenantResponse.model_validate(t) for t in tenants]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """Create a new tenant. Requires platform_admin role."""
    _require_platform_admin(auth_payload)

    # Check slug uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{body.slug}' already exists",
        )

    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        plan=body.plan,
        contact_email=body.contact_email,
        max_scans_per_day=body.max_scans_per_day,
        max_document_size=body.max_document_size,
        max_storage_mb=body.max_storage_mb,
        rate_limit_rpm=body.rate_limit_rpm,
        policy_config=body.policy_config.model_dump() if body.policy_config else None,
        siem_config=body.siem_config.model_dump() if body.siem_config else None,
        retention_days=body.retention_days,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    log.info(
        "tenant.created",
        tenant_id=str(tenant.id),
        slug=tenant.slug,
        plan=tenant.plan,
        created_by=auth_payload.get("sub"),
    )

    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """Get tenant details. Requires platform_admin role."""
    _require_platform_admin(auth_payload)

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return TenantResponse.model_validate(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """Update tenant settings. Requires platform_admin role."""
    _require_platform_admin(auth_payload)

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    update_data = body.model_dump(exclude_unset=True)
    # Pydantic sub-models must be serialized to plain dicts for JSONB columns
    for key in ("policy_config", "siem_config"):
        if key in update_data and isinstance(update_data[key], dict):
            pass  # already a dict from model_dump
    for field_name, value in update_data.items():
        setattr(tenant, field_name, value)

    await db.commit()
    await db.refresh(tenant)

    log.info(
        "tenant.updated",
        tenant_id=str(tenant.id),
        updated_fields=list(update_data.keys()),
        updated_by=auth_payload.get("sub"),
    )

    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def deactivate_tenant(
    tenant_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a tenant by setting is_active=False. Requires platform_admin role."""
    _require_platform_admin(auth_payload)

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.is_active = False
    await db.commit()

    log.info(
        "tenant.deactivated",
        tenant_id=str(tenant.id),
        slug=tenant.slug,
        deactivated_by=auth_payload.get("sub"),
    )
