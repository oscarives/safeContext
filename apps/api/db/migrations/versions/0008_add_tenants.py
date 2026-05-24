"""Add tenants table and tenant_id FK to operations and waivers.

Creates the tenants table for multi-tenant isolation (F6-A1).
Inserts a default tenant and backfills all existing operations and waivers.
Findings, redactions, and artifacts inherit tenant context via their
operation FK — no separate tenant_id column needed on those tables.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-23
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # ── 1. Create tenants table ─────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_scans_per_day", sa.Integer(), nullable=True),
        sa.Column("max_document_size", sa.Integer(), nullable=True),
        sa.Column("max_storage_mb", sa.Integer(), nullable=True),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "plan IN ('free', 'starter', 'enterprise')",
            name="ck_tenants_plan",
        ),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    # ── 2. Insert default tenant ────────────────────────────────────────────
    op.execute(f"""
        INSERT INTO tenants (id, name, slug, plan)
        VALUES ('{DEFAULT_TENANT_ID}', 'Default', 'default', 'free')
        ON CONFLICT (id) DO NOTHING
    """)

    # ── 3. Add tenant_id to operations ──────────────────────────────────────
    op.add_column(
        "operations",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,  # temporarily nullable for backfill
        ),
    )
    op.execute(f"UPDATE operations SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column("operations", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_operations_tenant_id",
        "operations",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_operations_tenant_id", "operations", ["tenant_id"])

    # ── 4. Add tenant_id to waivers ─────────────────────────────────────────
    op.add_column(
        "waivers",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute(f"UPDATE waivers SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL")
    op.alter_column("waivers", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_waivers_tenant_id",
        "waivers",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_waivers_tenant_id", "waivers", ["tenant_id"])


def downgrade() -> None:
    # Waivers
    op.drop_index("ix_waivers_tenant_id", table_name="waivers")
    op.drop_constraint("fk_waivers_tenant_id", "waivers", type_="foreignkey")
    op.drop_column("waivers", "tenant_id")

    # Operations
    op.drop_index("ix_operations_tenant_id", table_name="operations")
    op.drop_constraint("fk_operations_tenant_id", "operations", type_="foreignkey")
    op.drop_column("operations", "tenant_id")

    # Tenants table
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
