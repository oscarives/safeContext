"""Tests de schema E1.2 — verifican estructura sin base de datos real.

Criterios de aceptación:
- Las 5 tablas están definidas con los campos requeridos
- RLS está habilitado en la migración (DDL verificable)
- Los 5 índices requeridos están presentes en la migración
"""
import inspect

import pytest
import sqlalchemy as sa

from db.models import Artifact, Finding, Operation, Outbox, Redaction


class TestModelDefinitions:
    def test_operation_required_columns(self):
        cols = {c.name for c in Operation.__table__.columns}
        required = {
            "id", "trace_id", "actor_id", "actor_type", "document_id",
            "artifact_digest", "policy_version", "status", "created_at", "completed_at",
        }
        assert required.issubset(cols)

    def test_finding_required_columns(self):
        cols = {c.name for c in Finding.__table__.columns}
        required = {
            "id", "operation_id", "detector", "rule_id",
            "span_start", "span_end", "confidence", "severity", "explanation",
        }
        assert required.issubset(cols)

    def test_redaction_required_columns(self):
        cols = {c.name for c in Redaction.__table__.columns}
        required = {
            "id", "finding_id", "operation_id", "redaction_type",
            "policy_version", "applied_at", "approved_by", "approval_trace_id",
        }
        assert required.issubset(cols)

    def test_artifact_required_columns(self):
        cols = {c.name for c in Artifact.__table__.columns}
        required = {
            "id", "operation_id", "artifact_type",
            "minio_key", "digest", "worm_locked", "created_at",
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

    def test_required_indexes_present_in_migration(self):
        from db.migrations.versions import _0001_initial_schema as m
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
        from db.migrations.versions import _0001_initial_schema as m
        source = inspect.getsource(m.upgrade)
        tables = ["operations", "findings", "redactions", "artifacts", "outbox"]
        for table in tables:
            assert f"ENABLE ROW LEVEL SECURITY" in source, \
                "RLS not enabled in migration"

    def test_downgrade_drops_all_tables(self):
        from db.migrations.versions import _0001_initial_schema as m
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
