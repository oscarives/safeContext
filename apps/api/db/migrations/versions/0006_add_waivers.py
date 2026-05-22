"""Add waivers table for policy exception management.

Revision ID: b2c3d4e5f6a7
Revises: 3f8a1c9d2e47
Create Date: 2026-05-22
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "3f8a1c9d2e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE waivers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_id VARCHAR(128) NOT NULL,
            entity_pattern TEXT NOT NULL,
            justification TEXT NOT NULL,
            approved_by UUID NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active'
                CONSTRAINT waivers_status_check CHECK (status IN ('active', 'expired', 'revoked')),
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );
    """)
    op.execute("CREATE INDEX ix_waivers_rule_id ON waivers (rule_id);")
    op.execute("CREATE INDEX ix_waivers_status ON waivers (status);")
    op.execute(
        "CREATE INDEX ix_waivers_expires_at ON waivers (expires_at) WHERE expires_at IS NOT NULL;"
    )

    # Row-level security consistent with other tables
    op.execute("ALTER TABLE waivers ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE waivers FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenant_isolation ON waivers USING (true);")
    op.execute("""
        CREATE POLICY waiver_readonly ON waivers
            FOR SELECT
            USING (current_setting('app.current_role', true)
                   IN ('viewer', 'reviewer', 'admin', 'policy_editor'));
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS waivers;")
