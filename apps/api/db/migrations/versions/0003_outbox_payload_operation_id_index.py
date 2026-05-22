"""Add expression index on outbox.payload->>'operation_id'

Without this index, every lookup in _load_document_previews (review endpoint)
and in detector_agent / auditor_agent does a full table scan on the outbox
table using the JSONB path operator payload->>'operation_id'.
At high throughput this degrades linearly with outbox size.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expression index on the JSONB text extraction.
    # Supports: WHERE (payload->>'operation_id') = '...'
    #           WHERE (payload->>'operation_id') = ANY(ARRAY[...])
    op.create_index(
        "idx_outbox_payload_operation_id",
        "outbox",
        [sa.text("(payload->>'operation_id')")],
        postgresql_concurrently=False,  # set to True on live production tables
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_payload_operation_id", table_name="outbox")
