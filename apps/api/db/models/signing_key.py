"""SigningKey model — durable archive of Transit public keys (F8-1, ADR-015).

Each time the audit trail signs an operation (write-time) or anchors the chain,
the Vault Transit signature carries a ``key_version``. Verification of that
signature needs the matching **public** key. Today the public key is fetched
live from Vault at export time, so an export taken while Vault is down — or any
later attempt to verify after the key was rotated or the KMS decommissioned —
loses the ability to verify.

This table archives the public key (PEM) once per ``key_version`` so every
signed operation and every anchor stays verifiable **offline, forever, without
Vault and without trusting SafeContext**. That is the property that turns the
trail from "non-repudiation while Vault is alive" into portable, court-grade
evidence (ADR-015). The private key never leaves Vault (F7-3); only the public
half is stored here.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class SigningKey(Base):
    __tablename__ = "signing_keys"

    # The Transit key version (the N in "vault:vN:..."). Stable per version, so
    # the public key is archived exactly once and referenced by every signature
    # that carries this signing_key_version.
    key_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    # PEM-encoded public key exported from Vault Transit (ecdsa-p256).
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    # Algorithm hint for offline verifiers (e.g. "ecdsa-p256").
    algorithm: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
