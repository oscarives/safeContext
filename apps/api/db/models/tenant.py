"""Tenant model — multi-tenant isolation root entity."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base
from db.enums import TenantPlan


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "plan IN ('free', 'starter', 'enterprise')",
            name="ck_tenants_plan",
        ),
    )

    Plan = TenantPlan

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default=TenantPlan.FREE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Quota limits — NULL means unlimited
    max_scans_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_document_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bytes
    max_storage_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)

    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-tenant configuration (JSONB) — editable via admin API
    policy_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'")
    )
    siem_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'")
    )
    retention_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=text("365")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    operations: Mapped[list["Operation"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )
    waivers: Mapped[list["Waiver"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="tenant", cascade="all, delete-orphan"
    )
