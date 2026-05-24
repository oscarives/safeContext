"""Waiver management endpoints — T5.

POST   /v1/waivers              — create a new waiver (policy_editor or admin only)
GET    /v1/waivers              — list active non-expired waivers (any authenticated user)
DELETE /v1/waivers/{waiver_id}  — revoke a waiver (policy_editor or admin only)
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import get_roles, require_auth
from core.constants import DEFAULT_TENANT_ID
from db.models.waiver import Waiver
from db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(tags=["waivers"])

_PRIVILEGED_ROLES = ("policy_editor", "admin")


def _require_privileged(payload: dict) -> None:
    """Raise 403 if the caller lacks policy_editor or admin role."""
    roles = get_roles(payload)
    if not any(r in roles for r in _PRIVILEGED_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires policy_editor or admin role",
        )


# ── Request / Response schemas ────────────────────────────────────────────────


class WaiverCreate(BaseModel):
    rule_id: str
    entity_pattern: str
    justification: str
    expires_at: datetime | None = None


class WaiverResponse(BaseModel):
    id: uuid.UUID
    rule_id: str
    entity_pattern: str
    justification: str
    approved_by: uuid.UUID
    status: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/waivers", response_model=WaiverResponse, status_code=status.HTTP_201_CREATED)
async def create_waiver(
    body: WaiverCreate,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> WaiverResponse:
    """Create a new policy exception waiver.  Requires policy_editor or admin role."""
    _require_privileged(auth_payload)

    try:
        re.compile(body.entity_pattern)
    except re.error as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid regex in entity_pattern: {exc}",
        ) from exc

    approved_by = uuid.UUID(auth_payload["sub"])
    # Resolve tenant from JWT claim or fall back to default
    tenant_id_str = auth_payload.get("tenant_id", "")
    tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID
    waiver = Waiver(
        tenant_id=tenant_id,
        rule_id=body.rule_id,
        entity_pattern=body.entity_pattern,
        justification=body.justification,
        approved_by=approved_by,
        expires_at=body.expires_at,
    )
    db.add(waiver)
    await db.commit()
    await db.refresh(waiver)

    log.info(
        "waiver.created",
        waiver_id=str(waiver.id),
        rule_id=waiver.rule_id,
        approved_by=str(approved_by),
    )
    return WaiverResponse.model_validate(waiver)


@router.get("/waivers", response_model=list[WaiverResponse])
async def list_waivers(
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> list[WaiverResponse]:
    """Return all active waivers that have not yet expired.  Any authenticated user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Waiver)
        .where(Waiver.status == "active")
        .where((Waiver.expires_at.is_(None)) | (Waiver.expires_at > now))
        .order_by(Waiver.created_at.desc())
    )
    waivers = result.scalars().all()
    log.info("waiver.listed", count=len(waivers))
    return [WaiverResponse.model_validate(w) for w in waivers]


@router.delete("/waivers/{waiver_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_waiver(
    waiver_id: uuid.UUID,
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke an existing waiver.  Requires policy_editor or admin role."""
    _require_privileged(auth_payload)

    waiver = await db.get(Waiver, waiver_id)
    if waiver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Waiver not found")

    waiver.status = "revoked"
    await db.commit()

    log.info(
        "waiver.revoked",
        waiver_id=str(waiver_id),
        revoked_by=auth_payload.get("sub"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
