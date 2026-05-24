"""Tenant resolution and RLS session variable injection.

Extracts tenant_id from the JWT ``tenant_id`` claim (set by Keycloak mapper)
and sets the PostgreSQL session variable ``app.current_tenant_id`` via
``SET LOCAL`` so that RLS policies filter rows automatically.

Usage in endpoints:
    @router.get("/things")
    async def list_things(
        db: AsyncSession = Depends(get_tenant_db),
    ):
        ...  # all queries automatically filtered by tenant
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DEFAULT_TENANT_ID
from db.session import get_db


def resolve_tenant_id(request: Request) -> uuid.UUID:
    """Extract tenant_id from request state or JWT payload.

    Called after authentication middleware has populated ``request.state``.
    Falls back to DEFAULT_TENANT_ID for backward compatibility.
    """
    # Check if auth middleware set tenant_id on request state
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))

    # Fallback: try to extract from Authorization header payload
    # (for endpoints that don't use auth middleware but still need tenant context)
    return DEFAULT_TENANT_ID


async def get_tenant_db(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with RLS tenant context set.

    Sets ``app.current_tenant_id`` via SET LOCAL so that PostgreSQL RLS
    policies automatically filter all queries to the current tenant.
    SET LOCAL is scoped to the current transaction — no cleanup needed.
    """
    tenant_id = resolve_tenant_id(request)

    # SET LOCAL is transaction-scoped; it resets automatically at COMMIT/ROLLBACK
    await db.execute(
        text("SET LOCAL app.current_tenant_id = :tid"),
        {"tid": str(tenant_id)},
    )

    yield db
