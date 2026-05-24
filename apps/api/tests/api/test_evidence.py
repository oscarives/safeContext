"""Tests for F6-B evidence modules — TSA, chain hash, vault transit, WORM.

All external services (TSA, Vault, MinIO) are mocked.
"""
import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── F6-B1: TSA tests ────────────────────────────────────────────────────────


class TestTSA:
    @pytest.mark.asyncio
    async def test_request_tsa_token_success(self):
        from core.tsa import request_tsa_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Fake DER-encoded TSA response
        mock_response.content = b"\x30\x82\x00\x10" + b"\x00" * 100

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await request_tsa_token(b"test data", http_client=mock_client)

        assert result is not None
        assert result.token_b64  # non-empty base64 string
        assert result.tsa_url
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_tsa_token_timeout(self):
        import httpx
        from core.tsa import request_tsa_token

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        result = await request_tsa_token(b"test data", http_client=mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_request_tsa_token_http_error(self):
        from core.tsa import request_tsa_token

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await request_tsa_token(b"test data", http_client=mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_request_tsa_token_connect_error(self):
        import httpx
        from core.tsa import request_tsa_token

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await request_tsa_token(b"test data", http_client=mock_client)
        assert result is None

    def test_build_ts_request_returns_asn1(self):
        from core.tsa import _build_ts_request

        digest = hashlib.sha256(b"test").digest()
        req = _build_ts_request(digest)

        # Must start with ASN.1 SEQUENCE tag
        assert req[0] == 0x30
        # Must contain the SHA-256 digest
        assert digest in req

    def test_verify_tsa_digest_positive(self):
        from core.tsa import verify_tsa_digest

        digest = hashlib.sha256(b"test").digest()
        fake_token = b"\x30" + digest + b"\x00" * 50
        assert verify_tsa_digest(fake_token, digest) is True

    def test_verify_tsa_digest_negative(self):
        from core.tsa import verify_tsa_digest

        digest = hashlib.sha256(b"test").digest()
        wrong_digest = hashlib.sha256(b"wrong").digest()
        fake_token = b"\x30" + wrong_digest + b"\x00" * 50
        assert verify_tsa_digest(fake_token, digest) is False


# ── F6-B2: Chain hash tests ─────────────────────────────────────────────────


class TestChainHash:
    def test_compute_operation_hash_deterministic(self):
        from core.chain import compute_operation_hash

        op_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        trace_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        actor_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)

        h1 = compute_operation_hash(op_id, trace_id, actor_id, "abcdef", "completed", created)
        h2 = compute_operation_hash(op_id, trace_id, actor_id, "abcdef", "completed", created)

        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_compute_operation_hash_varies_with_input(self):
        from core.chain import compute_operation_hash

        op_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        trace_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        actor_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)

        h1 = compute_operation_hash(op_id, trace_id, actor_id, "digest1", "completed", created)
        h2 = compute_operation_hash(op_id, trace_id, actor_id, "digest2", "completed", created)

        assert h1 != h2

    def test_compute_chain_hash(self):
        from core.chain import GENESIS_HASH, compute_chain_hash

        op_hash = hashlib.sha256(b"operation-1").hexdigest()
        chain1 = compute_chain_hash(GENESIS_HASH, op_hash)

        assert len(chain1) == 64
        assert chain1 != GENESIS_HASH
        assert chain1 != op_hash

    def test_chain_hash_is_ordered(self):
        from core.chain import GENESIS_HASH, compute_chain_hash

        h1 = hashlib.sha256(b"op1").hexdigest()
        h2 = hashlib.sha256(b"op2").hexdigest()

        chain_a = compute_chain_hash(GENESIS_HASH, h1)
        chain_b = compute_chain_hash(chain_a, h2)

        # Reverse order should produce different chain
        chain_c = compute_chain_hash(GENESIS_HASH, h2)
        chain_d = compute_chain_hash(chain_c, h1)

        assert chain_b != chain_d

    @pytest.mark.asyncio
    async def test_verify_chain_empty(self):
        from core.chain import verify_chain

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        result = await verify_chain(mock_session, tenant_id)

        assert result["valid"] is True
        assert result["checked"] == 0

    @pytest.mark.asyncio
    async def test_verify_chain_valid(self):
        from core.chain import (
            GENESIS_HASH,
            compute_chain_hash,
            compute_operation_hash,
            verify_chain,
        )

        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)

        # Build a valid 2-link chain
        op1 = MagicMock()
        op1.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        op1.trace_id = uuid.UUID("aaaa1111-1111-1111-1111-111111111111")
        op1.actor_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        op1.tenant_id = tenant_id
        op1.artifact_digest = "digest1"
        op1.status = "completed"
        op1.created_at = created

        op1_hash = compute_operation_hash(
            op1.id, op1.trace_id, op1.actor_id, op1.artifact_digest, op1.status, op1.created_at
        )
        op1.chain_hash = compute_chain_hash(GENESIS_HASH, op1_hash)

        op2 = MagicMock()
        op2.id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        op2.trace_id = uuid.UUID("bbbb2222-2222-2222-2222-222222222222")
        op2.actor_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        op2.tenant_id = tenant_id
        op2.artifact_digest = "digest2"
        op2.status = "completed"
        op2.created_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

        op2_hash = compute_operation_hash(
            op2.id, op2.trace_id, op2.actor_id, op2.artifact_digest, op2.status, op2.created_at
        )
        op2.chain_hash = compute_chain_hash(op1.chain_hash, op2_hash)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [op1, op2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await verify_chain(mock_session, tenant_id)

        assert result["valid"] is True
        assert result["checked"] == 2

    @pytest.mark.asyncio
    async def test_verify_chain_broken(self):
        from core.chain import (
            GENESIS_HASH,
            compute_chain_hash,
            compute_operation_hash,
            verify_chain,
        )

        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)

        op1 = MagicMock()
        op1.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        op1.trace_id = uuid.UUID("aaaa1111-1111-1111-1111-111111111111")
        op1.actor_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        op1.tenant_id = tenant_id
        op1.artifact_digest = "digest1"
        op1.status = "completed"
        op1.created_at = created
        # TAMPERED chain_hash
        op1.chain_hash = "deadbeef" * 8

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [op1]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await verify_chain(mock_session, tenant_id)

        assert result["valid"] is False
        assert result["first_broken_at"] == str(op1.id)


# ── F6-B3: Vault Transit tests ──────────────────────────────────────────────


class TestVaultTransit:
    @pytest.mark.asyncio
    async def test_sign_data_success(self):
        from core.vault_transit import sign_data

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"signature": "vault:v1:AQID"}
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await sign_data(b"test data", http_client=mock_client)

        assert result == "AQID"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_sign_data_vault_unavailable(self):
        import httpx
        from core.vault_transit import sign_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await sign_data(b"test data", http_client=mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_sign_data_http_error(self):
        from core.vault_transit import sign_data

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await sign_data(b"test data", http_client=mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_public_key_success(self):
        from core.vault_transit import get_public_key

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "type": "ecdsa-p256",
                "keys": {
                    "1": {"public_key": "-----BEGIN PUBLIC KEY-----\nMFkw...\n-----END PUBLIC KEY-----"}
                },
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await get_public_key(http_client=mock_client)

        assert result is not None
        assert result["algorithm"] == "ecdsa-p256"
        assert "BEGIN PUBLIC KEY" in result["public_key_pem"]
        assert result["key_version"] == 1

    @pytest.mark.asyncio
    async def test_get_public_key_vault_unavailable(self):
        import httpx
        from core.vault_transit import get_public_key

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await get_public_key(http_client=mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_signature_success(self):
        from core.vault_transit import verify_signature

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"valid": True}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await verify_signature(b"data", "sig-base64", http_client=mock_client)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_signature_invalid(self):
        from core.vault_transit import verify_signature

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"valid": False}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await verify_signature(b"data", "bad-sig", http_client=mock_client)
        assert result is False


# ── F6-B4: WORM retention tests ─────────────────────────────────────────────


class TestWORM:
    def test_store_with_retention_no_minio(self):
        """When minio library isn't importable, store returns False gracefully."""
        from core.worm import store_with_retention

        with patch("core.worm._get_minio_client", return_value=None):
            result = store_with_retention("test/key", b"data")
            assert result is False

    def test_check_retention_no_minio(self):
        from core.worm import check_retention

        with patch("core.worm._get_minio_client", return_value=None):
            result = check_retention("test/key")
            assert result is None

    def test_store_with_retention_success(self):
        import sys
        from core.worm import store_with_retention

        mock_client = MagicMock()
        mock_client.put_object = MagicMock()

        # Mock minio modules that are imported inside store_with_retention
        mock_retention_mod = MagicMock()
        mock_commonconfig_mod = MagicMock()
        mock_commonconfig_mod.GOVERNANCE = "GOVERNANCE"

        with (
            patch("core.worm._get_minio_client", return_value=mock_client),
            patch.dict(sys.modules, {
                "minio": MagicMock(),
                "minio.retention": mock_retention_mod,
                "minio.commonconfig": mock_commonconfig_mod,
            }),
        ):
            result = store_with_retention(
                "tenant-a/trace-123/audit.json",
                b'{"test": true}',
                retention_days=365,
            )

        assert result is True
        mock_client.put_object.assert_called_once()

    def test_store_with_retention_failure(self):
        from core.worm import store_with_retention

        mock_client = MagicMock()
        mock_client.put_object = MagicMock(side_effect=Exception("S3 error"))

        with patch("core.worm._get_minio_client", return_value=mock_client):
            result = store_with_retention("key", b"data")

        assert result is False

    def test_default_retention_days(self):
        from core.worm import DEFAULT_RETENTION_DAYS
        # 7 years ≈ 2555 days
        assert DEFAULT_RETENTION_DAYS == 2555

    def test_delete_with_governance_bypass_no_minio(self):
        from core.worm import delete_with_governance_bypass

        with patch("core.worm._get_minio_client", return_value=None):
            result = delete_with_governance_bypass("test/key")
            assert result is False
