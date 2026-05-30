"""Archive Transit public keys for offline verification (F8-1, ADR-015).

F8-1: add ``signing_keys`` — one row per Transit key version holding the PEM
public key, so every signed operation/anchor stays verifiable offline (without
Vault, forever). Also add ``signing_public_key_pem`` to ``chain_anchors`` so an
exported anchor carries its own verification key.

All additions are nullable / new-table only — existing rows keep working.

Revision ID: f7a8b9c0d1e2
Revises: a2b3c4d5e6f7
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── F8-1: durable archive of Transit public keys ────────────────────────
    op.create_table(
        "signing_keys",
        sa.Column("key_version", sa.Integer(), primary_key=True),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── F8-3: anchor carries its own public key ─────────────────────────────
    op.add_column(
        "chain_anchors",
        sa.Column("signing_public_key_pem", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chain_anchors", "signing_public_key_pem")
    op.drop_table("signing_keys")
