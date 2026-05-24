"""Add policy_config, siem_config, retention_days to tenants.

Enables per-tenant configuration of:
- Detection policies (confidence thresholds, severity overrides, blocked entity types)
- SIEM integration (webhook, syslog, format)
- GDPR retention period

All columns are nullable with sensible server defaults so existing tenants
continue working without changes.

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-05-24
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("policy_config", JSONB, nullable=True, server_default="{}"),
    )
    op.add_column(
        "tenants",
        sa.Column("siem_config", JSONB, nullable=True, server_default="{}"),
    )
    op.add_column(
        "tenants",
        sa.Column("retention_days", sa.Integer, nullable=True, server_default="365"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "retention_days")
    op.drop_column("tenants", "siem_config")
    op.drop_column("tenants", "policy_config")
