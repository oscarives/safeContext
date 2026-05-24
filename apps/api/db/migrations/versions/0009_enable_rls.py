"""Enable Row-Level Security on tenant-scoped tables.

Creates RLS policies that filter rows by tenant_id matching the
PostgreSQL session variable ``app.current_tenant_id``. The API layer
sets this variable on each request via SET LOCAL (see db/session.py).

Superusers and migration roles bypass RLS by default in PostgreSQL,
so migrations continue to work without modification.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-23
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that have a direct tenant_id column
_TENANT_TABLES = ["operations", "waivers"]

# Tables that inherit tenant context through operations FK
# These need a sub-select RLS policy via operation_id → operations.tenant_id
_CHILD_TABLES = ["findings", "redactions", "artifacts"]


def upgrade() -> None:
    # ── Direct tenant_id tables ─────────────────────────────────────────────
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
                tenant_id = COALESCE(
                    current_setting('app.current_tenant_id', true)::uuid,
                    '00000000-0000-0000-0000-000000000000'::uuid
                )
            )
            WITH CHECK (
                tenant_id = COALESCE(
                    current_setting('app.current_tenant_id', true)::uuid,
                    '00000000-0000-0000-0000-000000000000'::uuid
                )
            )
        """)

    # ── Child tables (inherit tenant via operations FK) ─────────────────────
    for table in _CHILD_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
                operation_id IN (
                    SELECT id FROM operations
                    WHERE tenant_id = COALESCE(
                        current_setting('app.current_tenant_id', true)::uuid,
                        '00000000-0000-0000-0000-000000000000'::uuid
                    )
                )
            )
        """)

    # ── Create a non-superuser role for the app to use RLS ──────────────────
    # In production, the app connects as 'safecontext_app' (not postgres superuser).
    # Grant necessary permissions.  This is idempotent via IF NOT EXISTS.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'safecontext_app') THEN
                CREATE ROLE safecontext_app LOGIN;
            END IF;
        END
        $$
    """)
    for table in _TENANT_TABLES + _CHILD_TABLES + ["outbox", "tenants"]:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO safecontext_app")


def downgrade() -> None:
    for table in _CHILD_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
