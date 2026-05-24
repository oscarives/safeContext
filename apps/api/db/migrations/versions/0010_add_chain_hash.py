"""Add chain_hash column to operations for tamper detection (F6-B2).

Each completed operation gets a chain_hash = SHA256(prev_chain_hash + operation_hash),
forming a lightweight hash chain that enables detection of tampering or deletion.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-23
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("operations", sa.Column("chain_hash", sa.Text(), nullable=True))
    op.create_index("ix_operations_chain_hash", "operations", ["chain_hash"])


def downgrade() -> None:
    op.drop_index("ix_operations_chain_hash", table_name="operations")
    op.drop_column("operations", "chain_hash")
