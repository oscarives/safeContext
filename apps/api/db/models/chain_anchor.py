"""ChainAnchor model — signed checkpoints of the per-tenant hash chain (F7-6).

Anchoring periodically signs the current chain head with the asymmetric Vault
Transit key (and optionally a TSA token). This turns the chain from
tamper-evident into tamper-proof: an insider with DB write access can recompute
the SHA256 chain, but cannot forge the asymmetric signature over the head, so
verification against the latest anchor detects the rewrite (ADR-014/H3).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class ChainAnchor(Base):
    __tablename__ = "chain_anchors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The chain_hash of the most recent operation at anchoring time.
    chain_head_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # How many operations the chain covered when this anchor was taken.
    operations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Asymmetric signature over chain_head_hash.
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PEM public key of signing_key_version, archived with the anchor so the
    # anchor verifies offline without Vault or the signing_keys table (F8-3).
    signing_public_key_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional RFC 3161 timestamp token over the chain head.
    tsa_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
