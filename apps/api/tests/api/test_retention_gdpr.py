"""Tests for F6-C5 GDPR retention & purge with deletion certificates.

All DB and WORM interactions are mocked.
"""
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.constants import DEFAULT_TENANT_ID

# ── Tests ────────────────────────────────────────────────────────────────────


class TestDeletionCertificate:
    def test_certificate_to_dict(self):
        from core.retention_gdpr import DeletionCertificate

        cert = DeletionCertificate(
            certificate_id="cert-123",
            tenant_id=str(DEFAULT_TENANT_ID),
            deleted_at="2026-01-01T00:00:00+00:00",
            retention_days=365,
            cutoff_date="2025-01-01T00:00:00+00:00",
            operations_deleted=5,
            operation_ids=["op-1", "op-2", "op-3", "op-4", "op-5"],
            findings_deleted=10,
            redactions_deleted=3,
            artifacts_deleted=5,
            deletion_reason="GDPR retention policy: 365 days",
            executor="retention-purge-job",
        )

        d = cert.to_dict()
        assert d["certificate_type"] == "gdpr_deletion"
        assert d["deleted_records"]["operations"] == 5
        assert d["deleted_records"]["findings"] == 10
        assert len(d["deleted_records"]["operation_ids"]) == 5
        assert d["signature"] is None

    def test_certificate_sign(self):
        from core.retention_gdpr import DeletionCertificate

        cert = DeletionCertificate(
            certificate_id="cert-456",
            tenant_id="tenant-abc",
            deleted_at="2026-06-01T00:00:00+00:00",
            retention_days=90,
            cutoff_date="2026-03-03T00:00:00+00:00",
            operations_deleted=2,
            operation_ids=["a", "b"],
            findings_deleted=4,
            redactions_deleted=1,
            artifacts_deleted=2,
            deletion_reason="GDPR retention policy: 90 days",
            executor="test",
        )

        sig = cert.sign("test-secret")
        assert len(sig) == 64  # SHA-256 hex digest
        assert cert.signature == sig

        # Verify the signature manually
        payload = cert.to_dict()
        payload.pop("signature")
        data = json.dumps(payload, sort_keys=True, default=str).encode()
        expected = hmac.new(b"test-secret", data, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_certificate_sign_deterministic(self):
        from core.retention_gdpr import DeletionCertificate

        cert1 = DeletionCertificate(
            certificate_id="cert-same",
            tenant_id="t",
            deleted_at="2026-01-01",
            retention_days=365,
            cutoff_date="2025-01-01",
            operations_deleted=1,
            operation_ids=["op1"],
            findings_deleted=0,
            redactions_deleted=0,
            artifacts_deleted=0,
            deletion_reason="test",
            executor="test",
        )
        cert2 = DeletionCertificate(
            certificate_id="cert-same",
            tenant_id="t",
            deleted_at="2026-01-01",
            retention_days=365,
            cutoff_date="2025-01-01",
            operations_deleted=1,
            operation_ids=["op1"],
            findings_deleted=0,
            redactions_deleted=0,
            artifacts_deleted=0,
            deletion_reason="test",
            executor="test",
        )

        assert cert1.sign("key") == cert2.sign("key")


class TestFindExpiredOperations:
    @pytest.mark.asyncio
    async def test_returns_expired_ops(self):
        from core.retention_gdpr import find_expired_operations

        old_op = MagicMock()
        old_op.id = uuid.uuid4()
        old_op.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [old_op]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await find_expired_operations(mock_session, DEFAULT_TENANT_ID, retention_days=365)
        assert len(result) == 1
        assert result[0].id == old_op.id

    @pytest.mark.asyncio
    async def test_returns_empty_when_nothing_expired(self):
        from core.retention_gdpr import find_expired_operations

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await find_expired_operations(mock_session, DEFAULT_TENANT_ID)
        assert result == []


class TestDeleteOperations:
    @pytest.mark.asyncio
    async def test_delete_counts_returned(self):
        from core.retention_gdpr import delete_operations

        cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        mock_session = AsyncMock()
        # Mock the count queries (3 counts) + 1 delete
        count_results = [
            MagicMock(scalar=MagicMock(return_value=10)),  # findings
            MagicMock(scalar=MagicMock(return_value=3)),   # redactions
            MagicMock(scalar=MagicMock(return_value=5)),   # artifacts
            MagicMock(rowcount=7),                         # operations deleted
        ]
        mock_session.execute = AsyncMock(side_effect=count_results)

        result = await delete_operations(mock_session, DEFAULT_TENANT_ID, cutoff)
        assert result["operations"] == 7
        assert result["findings"] == 10
        assert result["redactions"] == 3
        assert result["artifacts"] == 5


class TestRunGdprPurge:
    @pytest.mark.asyncio
    async def test_nothing_to_purge(self):
        from core.retention_gdpr import run_gdpr_purge

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await run_gdpr_purge(mock_session, DEFAULT_TENANT_ID)
        assert result["purged"] is False
        assert result["operations_deleted"] == 0
        assert result["certificate_id"] is None

    @pytest.mark.asyncio
    async def test_purge_with_certificate(self):
        from core.retention_gdpr import run_gdpr_purge

        old_op = MagicMock()
        old_op.id = uuid.uuid4()
        old_op.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        mock_session = AsyncMock()

        # First call: find_expired_operations (returns scalars)
        find_result = MagicMock()
        find_scalars = MagicMock()
        find_scalars.all.return_value = [old_op]
        find_result.scalars.return_value = find_scalars

        # Then: count queries (3) + delete (1)
        count_findings = MagicMock(scalar=MagicMock(return_value=5))
        count_redactions = MagicMock(scalar=MagicMock(return_value=2))
        count_artifacts = MagicMock(scalar=MagicMock(return_value=3))
        delete_result = MagicMock(rowcount=1)

        mock_session.execute = AsyncMock(
            side_effect=[find_result, count_findings, count_redactions, count_artifacts, delete_result]
        )
        mock_session.commit = AsyncMock()

        with patch("core.retention_gdpr.store_deletion_certificate", AsyncMock(return_value=True)):
            result = await run_gdpr_purge(mock_session, DEFAULT_TENANT_ID, retention_days=365)

        assert result["purged"] is True
        assert result["operations_deleted"] == 1
        assert result["findings_deleted"] == 5
        assert result["certificate_id"] is not None
        assert result["certificate_stored"] is True
        assert result["certificate"]["certificate_type"] == "gdpr_deletion"
        assert result["certificate"]["signature"] is not None

    @pytest.mark.asyncio
    async def test_purge_certificate_store_failure_graceful(self):
        from core.retention_gdpr import run_gdpr_purge

        old_op = MagicMock()
        old_op.id = uuid.uuid4()
        old_op.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        mock_session = AsyncMock()
        find_result = MagicMock()
        find_scalars = MagicMock()
        find_scalars.all.return_value = [old_op]
        find_result.scalars.return_value = find_scalars

        mock_session.execute = AsyncMock(
            side_effect=[
                find_result,
                MagicMock(scalar=MagicMock(return_value=0)),
                MagicMock(scalar=MagicMock(return_value=0)),
                MagicMock(scalar=MagicMock(return_value=0)),
                MagicMock(rowcount=1),
            ]
        )
        mock_session.commit = AsyncMock()

        with patch("core.retention_gdpr.store_deletion_certificate", AsyncMock(return_value=False)):
            result = await run_gdpr_purge(mock_session, DEFAULT_TENANT_ID)

        assert result["purged"] is True
        assert result["certificate_stored"] is False


class TestStoreDeletionCertificate:
    @pytest.mark.asyncio
    async def test_store_success(self):
        from core.retention_gdpr import DeletionCertificate, store_deletion_certificate

        cert = DeletionCertificate(
            certificate_id="cert-store-ok",
            tenant_id="t",
            deleted_at="2026-01-01",
            retention_days=365,
            cutoff_date="2025-01-01",
            operations_deleted=1,
            operation_ids=["op1"],
            findings_deleted=0,
            redactions_deleted=0,
            artifacts_deleted=0,
            deletion_reason="test",
            executor="test",
        )
        cert.sign("secret")

        with patch("core.worm.store_with_retention", return_value=True) as mock_store:
            result = await store_deletion_certificate(cert)

        assert result is True
        mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_failure_graceful(self):
        from core.retention_gdpr import DeletionCertificate, store_deletion_certificate

        cert = DeletionCertificate(
            certificate_id="cert-fail",
            tenant_id="t",
            deleted_at="2026-01-01",
            retention_days=365,
            cutoff_date="2025-01-01",
            operations_deleted=0,
            operation_ids=[],
            findings_deleted=0,
            redactions_deleted=0,
            artifacts_deleted=0,
            deletion_reason="test",
            executor="test",
        )

        with patch("core.worm.store_with_retention", side_effect=Exception("S3 down")):
            result = await store_deletion_certificate(cert)

        assert result is False
