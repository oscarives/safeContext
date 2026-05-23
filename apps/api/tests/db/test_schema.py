"""Tests de schema E1.2 — verifican estructura sin base de datos real.

Criterios de aceptación:
- Las 5 tablas están definidas con los campos requeridos
- RLS está habilitado en la migración (DDL verificable)
- Los 5 índices requeridos están presentes en la migración
"""

import inspect

from db.models import Artifact, Finding, Operation, Outbox, Redaction


class TestModelDefinitions:
    def test_operation_required_columns(self):
        cols = {c.name for c in Operation.__table__.columns}
        required = {
            "id",
            "trace_id",
            "actor_id",
            "actor_type",
            "document_id",
            "artifact_digest",
            "policy_version",
            "status",
            "created_at",
            "completed_at",
        }
        assert required.issubset(cols)

    def test_finding_required_columns(self):
        cols = {c.name for c in Finding.__table__.columns}
        required = {
            "id",
            "operation_id",
            "detector",
            "rule_id",
            "span_start",
            "span_end",
            "confidence",
            "severity",
            "explanation",
        }
        assert required.issubset(cols)

    def test_redaction_required_columns(self):
        cols = {c.name for c in Redaction.__table__.columns}
        required = {
            "id",
            "finding_id",
            "operation_id",
            "redaction_type",
            "policy_version",
            "applied_at",
            "approved_by",
            "approval_trace_id",
        }
        assert required.issubset(cols)

    def test_artifact_required_columns(self):
        cols = {c.name for c in Artifact.__table__.columns}
        required = {
            "id",
            "operation_id",
            "artifact_type",
            "minio_key",
            "digest",
            "worm_locked",
            "created_at",
        }
        assert required.issubset(cols)

    def test_outbox_required_columns(self):
        cols = {c.name for c in Outbox.__table__.columns}
        required = {"id", "event_type", "payload", "processed", "created_at"}
        assert required.issubset(cols)


class TestConstraints:
    def test_operation_actor_type_constraint(self):
        constraints = {c.name for c in Operation.__table__.constraints}
        assert "ck_operations_actor_type" in constraints

    def test_operation_status_constraint(self):
        constraints = {c.name for c in Operation.__table__.constraints}
        assert "ck_operations_status" in constraints

    def test_finding_severity_constraint(self):
        constraints = {c.name for c in Finding.__table__.constraints}
        assert "ck_findings_severity" in constraints

    def test_finding_confidence_range_constraint(self):
        constraints = {c.name for c in Finding.__table__.constraints}
        assert "ck_findings_confidence_range" in constraints

    def test_redaction_type_constraint(self):
        constraints = {c.name for c in Redaction.__table__.constraints}
        assert "ck_redactions_type" in constraints

    def test_artifact_type_constraint(self):
        constraints = {c.name for c in Artifact.__table__.constraints}
        assert "ck_artifacts_type" in constraints


class TestIndexesInMigration:
    """Verifica que los índices requeridos están en la migración 0001."""

    @staticmethod
    def _load_migration():
        """Load 0001_initial_schema.py using importlib (name starts with digit)."""
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).parent.parent.parent
            / "db"
            / "migrations"
            / "versions"
            / "0001_initial_schema.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0001", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_required_indexes_present_in_migration(self):
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        required_indexes = [
            "idx_operations_trace_id",
            "idx_operations_actor_id",
            "idx_findings_operation_id",
            "idx_artifacts_operation_id",
            "idx_outbox_processed",
        ]
        for idx in required_indexes:
            assert idx in source, f"Index {idx} not found in migration upgrade()"

    def test_rls_enabled_in_migration(self):
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source, "RLS not enabled in migration"

    def test_downgrade_drops_all_tables(self):
        m = self._load_migration()
        source = inspect.getsource(m.downgrade)
        tables = ["outbox", "artifacts", "redactions", "findings", "operations"]
        for table in tables:
            assert table in source, f"Table {table} not dropped in downgrade()"


class TestRelationships:
    def test_operation_has_findings_relationship(self):
        assert hasattr(Operation, "findings")

    def test_operation_has_redactions_relationship(self):
        assert hasattr(Operation, "redactions")

    def test_operation_has_artifacts_relationship(self):
        assert hasattr(Operation, "artifacts")

    def test_finding_has_redactions_relationship(self):
        assert hasattr(Finding, "redactions")


class TestPartitionMigration:
    """Verify that migration 0005 defines the expected partitioning DDL."""

    @staticmethod
    def _load_migration():
        """Load 0005_partition_operations_findings.py via importlib."""
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).parent.parent.parent
            / "db"
            / "migrations"
            / "versions"
            / "0005_partition_operations_findings.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0005", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_revision_metadata(self):
        """Migration must declare correct revision chain."""
        m = self._load_migration()
        assert m.revision == "3f8a1c9d2e47"
        assert m.down_revision == "0004"

    def test_upgrade_creates_partitioned_table(self):
        """upgrade() must create the PARTITION BY RANGE table."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "PARTITION BY RANGE" in source
        assert "operations_partitioned" in source

    def test_upgrade_creates_24_monthly_partitions(self):
        """upgrade() must define 24 monthly partitions (2025-01 to 2026-12)."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)

        # The migration uses a dynamic loop over a `months` list of
        # (start, end) tuples and generates partition names at runtime via
        # f"operations_y{year}m{month}".  We verify:
        # 1. The naming pattern is correct
        assert 'operations_y{year}m{month}' in source, (
            "Partition naming pattern not found in upgrade()"
        )

        # 2. All 24 monthly date ranges are declared in the months list
        expected_ranges = []
        for y in (2025, 2026):
            for mo in range(1, 13):
                expected_ranges.append(f'"{y}-{mo:02d}-01"')
        for date_str in expected_ranges:
            assert date_str in source, (
                f"Date boundary {date_str} not found in upgrade() months list"
            )

        # 3. The months list has exactly 24 date-range tuples
        #    Each tuple appears as ("YYYY-MM-DD", "YYYY-MM-DD") in source
        import re
        tuple_pattern = re.findall(r'\("\d{4}-\d{2}-\d{2}",\s*"\d{4}-\d{2}-\d{2}"\)', source)
        assert len(tuple_pattern) == 24, (
            f"Expected 24 monthly range tuples in months list, found {len(tuple_pattern)}"
        )

    def test_upgrade_creates_default_partition(self):
        """upgrade() must include a DEFAULT catch-all partition."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "operations_future" in source
        assert "DEFAULT" in source

    def test_upgrade_copies_data(self):
        """upgrade() must migrate existing rows into the partitioned table."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "INSERT INTO operations_partitioned SELECT * FROM operations" in source

    def test_upgrade_atomic_rename_swap(self):
        """upgrade() must perform the old/new rename swap."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "operations_old" in source
        assert "RENAME TO operations_old" in source
        assert "RENAME TO operations" in source

    def test_upgrade_recreates_child_fk_constraints(self):
        """upgrade() must drop and recreate FKs for all child tables."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        child_constraints = [
            "findings_operation_id_fkey",
            "redactions_operation_id_fkey",
            "artifacts_operation_id_fkey",
        ]
        for constraint in child_constraints:
            assert constraint in source, (
                f"FK constraint {constraint} not handled in upgrade()"
            )

    def test_upgrade_reenables_rls(self):
        """upgrade() must re-enable RLS on the new partitioned parent."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source

    def test_upgrade_drops_old_table(self):
        """upgrade() must clean up the original non-partitioned table."""
        m = self._load_migration()
        source = inspect.getsource(m.upgrade)
        assert "DROP TABLE operations_old" in source

    def test_downgrade_raises(self):
        """downgrade() must raise NotImplementedError — no safe auto-rollback."""
        import pytest
        m = self._load_migration()
        with pytest.raises(NotImplementedError):
            m.downgrade()
