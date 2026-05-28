"""Write-time signature columns + chain_anchors table (F7-5/F7-6, ADR-014).

F7-5 (H1): add ``event_signature``, ``event_signed_at`` and
``signing_key_version`` to ``operations`` so each completed operation carries an
asymmetric signature produced at write-time (bound to the event as it occurred).

F7-6 (H3): add ``chain_anchors`` — periodic signed checkpoints of the per-tenant
chain head. Anchoring the head with the asymmetric key (and optionally a TSA
token) turns the chain from tamper-evident into tamper-proof: an insider who
recomputes the chain cannot forge the signed anchor.

All new columns are nullable so existing operations keep working unchanged.

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── F7-5: write-time signature on operations ────────────────────────────
    op.add_column("operations", sa.Column("event_signature", sa.Text(), nullable=True))
    op.add_column(
        "operations",
        sa.Column("event_signed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "operations", sa.Column("signing_key_version", sa.Integer(), nullable=True)
    )

    # ── F7-6: signed chain head anchors ─────────────────────────────────────
    op.create_table(
        "chain_anchors",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chain_head_hash", sa.Text(), nullable=False),
        sa.Column("operations_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signing_key_version", sa.Integer(), nullable=True),
        sa.Column("tsa_token", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_chain_anchors_tenant_created",
        "chain_anchors",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chain_anchors_tenant_created", table_name="chain_anchors")
    op.drop_table("chain_anchors")
    op.drop_column("operations", "signing_key_version")
    op.drop_column("operations", "event_signed_at")
    op.drop_column("operations", "event_signature")
