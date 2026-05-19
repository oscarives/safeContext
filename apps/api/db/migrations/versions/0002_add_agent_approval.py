"""Add approved_by_agent_id to redactions for MCP agent approvals

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "redactions",
        sa.Column("approved_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Comment explains the field
    op.execute("""
        COMMENT ON COLUMN redactions.approved_by_agent_id IS
        'agent client_id that approved this finding via safecontext.approve MCP tool (F4+)'
    """)


def downgrade() -> None:
    op.drop_column("redactions", "approved_by_agent_id")
