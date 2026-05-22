"""Add sanitized_text to operations and index on artifact_digest.

sanitized_text: stores the document with PII spans replaced by [REDACTED].
  Set by sanitizer_agent after processing. Null until sanitization completes.
  Allows MCP and API clients to retrieve the safe version of the document.

artifact_digest index: enables O(log n) lookup for deduplication.
  When the same document is submitted again, the API can return the previous
  result immediately without re-running the full detection pipeline.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Column for the sanitized document text
    op.add_column(
        "operations",
        sa.Column("sanitized_text", sa.Text, nullable=True),
    )

    # Index on artifact_digest for fast deduplication lookups
    op.create_index(
        "idx_operations_artifact_digest",
        "operations",
        ["artifact_digest"],
    )


def downgrade() -> None:
    op.drop_index("idx_operations_artifact_digest", table_name="operations")
    op.drop_column("operations", "sanitized_text")
