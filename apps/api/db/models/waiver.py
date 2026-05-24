"""Waiver model — approved exceptions to policy enforcement."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base


class Waiver(Base):
    __tablename__ = "waivers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="waivers_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_pattern: Mapped[str] = mapped_column(Text, nullable=False)  # regex pattern
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="waivers")  # type: ignore[name-defined]  # noqa: F821
