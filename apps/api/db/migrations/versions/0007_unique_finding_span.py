"""Add UNIQUE constraint on findings(operation_id, rule_id, span_start, span_end).

Prevents duplicate findings for the same span within an operation.
Pre-release: no production data exists, but the migration safely removes
duplicates (keeping oldest by id) before creating the constraint.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Remove duplicates (keep oldest by id)
    op.execute("""
        DELETE FROM findings f1
        USING findings f2
        WHERE f1.operation_id = f2.operation_id
          AND f1.rule_id = f2.rule_id
          AND f1.span_start = f2.span_start
          AND f1.span_end = f2.span_end
          AND f1.id > f2.id
    """)

    # Step 2: Create unique constraint
    op.create_unique_constraint(
        "uq_finding_operation_rule_span",
        "findings",
        ["operation_id", "rule_id", "span_start", "span_end"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_finding_operation_rule_span", "findings")
