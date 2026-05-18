"""Initial schema: operations, findings, redactions, artifacts, outbox

Revision ID: 0001
Revises:
Create Date: 2026-05-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── operations ────────────────────────────────────────────────────────────
    op.create_table(
        "operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_digest", sa.Text, nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "actor_type IN ('human', 'mcp_agent', 'pipeline')",
            name="ck_operations_actor_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'escalated', 'approved', 'rejected')",
            name="ck_operations_status",
        ),
    )
    op.execute("ALTER TABLE operations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON operations
        USING (true)
    """)
    op.execute("""
        CREATE POLICY viewer_readonly ON operations
        FOR SELECT
        USING (current_setting('app.current_role', true)
               IN ('viewer', 'reviewer', 'admin', 'policy_editor'))
    """)
    # security_barrier is set via init-pgaudit.sql at postgres init time

    # ── findings ──────────────────────────────────────────────────────────────
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detector", sa.Text, nullable=False),
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column("span_start", sa.Integer, nullable=False),
        sa.Column("span_end", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("explanation", postgresql.JSONB, nullable=False),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_findings_confidence_range",
        ),
    )
    op.execute("ALTER TABLE findings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE findings FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON findings USING (true)")
    # security_barrier is set via init-pgaudit.sql at postgres init time

    # ── redactions ────────────────────────────────────────────────────────────
    op.create_table(
        "redactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redaction_type", sa.String(20), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "redaction_type IN ('mask', 'remove', 'replace')",
            name="ck_redactions_type",
        ),
    )
    op.execute("ALTER TABLE redactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE redactions FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON redactions USING (true)")

    # ── artifacts ─────────────────────────────────────────────────────────────
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(20), nullable=False),
        sa.Column("minio_key", sa.Text, nullable=False),
        sa.Column("digest", sa.Text, nullable=False),
        sa.Column("worm_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "artifact_type IN ('original', 'sanitized', 'audit_export')",
            name="ck_artifacts_type",
        ),
    )
    op.execute("ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE artifacts FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON artifacts USING (true)")

    # ── outbox ────────────────────────────────────────────────────────────────
    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("processed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outbox FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON outbox USING (true)")

    # ── indexes ───────────────────────────────────────────────────────────────
    op.create_index("idx_operations_trace_id", "operations", ["trace_id"], postgresql_concurrently=False)
    op.create_index("idx_operations_actor_id", "operations", ["actor_id"], postgresql_concurrently=False)
    op.create_index("idx_findings_operation_id", "findings", ["operation_id"], postgresql_concurrently=False)
    op.create_index("idx_artifacts_operation_id", "artifacts", ["operation_id"], postgresql_concurrently=False)
    op.create_index(
        "idx_outbox_processed",
        "outbox",
        ["processed"],
        postgresql_where=sa.text("processed = false"),
        postgresql_concurrently=False,
    )


def downgrade() -> None:
    # Drop in reverse FK order
    op.drop_table("outbox")
    op.drop_table("artifacts")
    op.drop_table("redactions")
    op.drop_table("findings")
    op.drop_table("operations")
