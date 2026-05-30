"""Write-time evidence sealing for the operation audit trail (F7-5, ADR-014/H1).

This module lives in the shared ``db`` package on purpose: both the API image
(``apps/api``) and the worker image (``apps/workers``) copy ``apps/api/db`` onto
their PYTHONPATH, but neither shares ``apps/api/core``. The real completion point
for the automated scan pipeline is the ``auditor_agent`` worker, which therefore
must be able to seal the operation without importing ``core.*``.

Sealing happens **at the moment the operation completes** (write-time), not when
the audit export is read (read-time). It does two things:

1. **Chain hash** (always, deterministic, no network): populates
   ``operation.chain_hash`` so the per-tenant hash chain is actually built. Before
   F7-5 the chain functions had no caller and ``chain_hash`` was never set, so the
   custody chain was inexistent in practice (ADR-014/H3).

2. **Asymmetric signature** (best-effort, needs Vault): signs the canonical
   ``operation_hash`` with the Vault Transit ECDSA-P256 key and persists the
   signature + ``signed_at`` + key version on the row. This is the real
   non-repudiation evidence — bound to the event as it occurred, not to a later
   view of the database (ADR-014/H1).

The pure hash helpers (``compute_operation_hash`` / ``compute_chain_hash`` /
``get_latest_chain_hash`` / ``GENESIS_HASH``) are defined here and re-exported by
``core.chain`` so there is a single source of truth shared by the chain verifier
(API) and the write-time sealer (worker).
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Genesis hash — used as prev_chain_hash for the first operation in a chain.
GENESIS_HASH = "0" * 64

_VAULT_TIMEOUT = 5.0


# ── Pure chain primitives (no I/O) ──────────────────────────────────────────


def compute_operation_hash(
    operation_id: UUID,
    trace_id: UUID,
    actor_id: UUID,
    artifact_digest: str,
    status: str,
    created_at: datetime,
) -> str:
    """Compute the content hash of an individual operation."""
    content = json.dumps(
        {
            "id": str(operation_id),
            "trace_id": str(trace_id),
            "actor_id": str(actor_id),
            "artifact_digest": artifact_digest,
            "status": status,
            "created_at": created_at.isoformat() if created_at else "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def compute_chain_hash(prev_chain_hash: str, operation_hash: str) -> str:
    """Compute chain_hash = SHA256(prev_chain_hash || operation_hash)."""
    combined = f"{prev_chain_hash}{operation_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()


async def get_latest_chain_hash(db: AsyncSession, tenant_id: UUID) -> str:
    """Get the chain_hash of the most recent operation for a tenant.

    Returns GENESIS_HASH if no operations exist or none have chain_hash set.
    """
    from db.models.operation import Operation

    result = await db.execute(
        select(Operation.chain_hash)
        .where(
            Operation.tenant_id == tenant_id,
            Operation.chain_hash.isnot(None),
        )
        .order_by(Operation.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    return latest or GENESIS_HASH


# ── Vault Transit signer (self-contained — no dependency on core.*) ──────────


async def sign_operation_hash(
    operation_hash_hex: str,
    *,
    vault_addr: str,
    vault_token: str,
    vault_key: str,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[str | None, int | None]:
    """Sign the operation hash with the Vault Transit ECDSA-P256 key.

    Returns ``(signature_b64, key_version)`` on success or ``(None, None)`` on any
    failure (Vault down, timeout, misconfig). Write-time signing is best-effort:
    if it fails the chain hash is still set, and the read-time export can enforce
    ``audit_require_digital_signature`` (F7-4) to refuse exports without a
    signature in production.

    Mirrors the fixes from F7-1/F7-2/F7-3: the key is ecdsa-p256 so no RSA-only
    ``signature_algorithm`` is sent, and the real key version is parsed from the
    ``vault:vN:`` prefix instead of being assumed to be v1.
    """
    # Sign the raw 32-byte digest (decoded from hex), base64-encoded for Vault.
    data = bytes.fromhex(operation_hash_hex)
    input_b64 = base64.b64encode(data).decode("ascii")
    url = f"{vault_addr}/v1/transit/sign/{vault_key}"
    headers = {"X-Vault-Token": vault_token, "Content-Type": "application/json"}
    payload = {"input": input_b64, "hash_algorithm": "sha2-256"}

    async def _post(client: httpx.AsyncClient) -> tuple[str | None, int | None]:
        resp = await client.post(url, headers=headers, json=payload, timeout=_VAULT_TIMEOUT)
        if resp.status_code != 200:
            log.warning("evidence.sign_failed", status=resp.status_code, key=vault_key)
            return None, None
        sig = resp.json().get("data", {}).get("signature", "")
        # Vault returns "vault:vN:<base64>" — keep the full token and parse N.
        key_version = 1
        if sig.startswith("vault:"):
            parts = sig.split(":", 2)
            if len(parts) == 3:
                try:
                    key_version = int(parts[1].lstrip("v"))
                except ValueError:
                    key_version = 1
        return sig, key_version

    try:
        if http_client:
            return await _post(http_client)
        async with httpx.AsyncClient() as client:
            return await _post(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("evidence.sign_error", error=str(exc), key=vault_key)
        return None, None


async def get_transit_public_key(
    *,
    vault_addr: str,
    vault_token: str,
    vault_key: str,
    key_version: int | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[str | None, str | None]:
    """Fetch the PEM public key for a Transit key version (F8-1, ADR-015).

    Returns ``(public_key_pem, algorithm)`` or ``(None, None)`` on any failure.
    Reads ``transit/keys/{key}`` (no private material — ``exportable=false`` keys
    still expose the public half here) and picks the entry for ``key_version``
    (or the latest version if not given).
    """
    url = f"{vault_addr}/v1/transit/keys/{vault_key}"
    headers = {"X-Vault-Token": vault_token}

    async def _get(client: httpx.AsyncClient) -> tuple[str | None, str | None]:
        resp = await client.get(url, headers=headers, timeout=_VAULT_TIMEOUT)
        if resp.status_code != 200:
            log.warning("evidence.pubkey_failed", status=resp.status_code, key=vault_key)
            return None, None
        data = resp.json().get("data", {})
        algorithm = data.get("type")
        keys = data.get("keys", {})
        ver = str(key_version if key_version is not None else data.get("latest_version", ""))
        entry = keys.get(ver) or {}
        pem = entry.get("public_key") if isinstance(entry, dict) else None
        return (pem or None), algorithm

    try:
        if http_client:
            return await _get(http_client)
        async with httpx.AsyncClient() as client:
            return await _get(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("evidence.pubkey_error", error=str(exc), key=vault_key)
        return None, None


async def archive_public_key_if_needed(
    db: AsyncSession,
    key_version: int,
    *,
    vault_addr: str,
    vault_token: str,
    vault_key: str,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Idempotently archive the PEM public key for ``key_version`` (F8-2).

    Skips the Vault round-trip if the version is already archived, so signing N
    operations with the same key version costs at most one extra fetch. Stores
    nothing (and never raises) if Vault is unavailable — archival is best-effort,
    exactly like write-time signing.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.models.signing_key import SigningKey

    try:
        existing = await db.execute(
            select(SigningKey.key_version).where(SigningKey.key_version == key_version)
        )
        if existing.scalar_one_or_none() is not None:
            return
        pem, algorithm = await get_transit_public_key(
            vault_addr=vault_addr,
            vault_token=vault_token,
            vault_key=vault_key,
            key_version=key_version,
            http_client=http_client,
        )
        if not pem:
            return
        stmt = (
            pg_insert(SigningKey)
            .values(key_version=key_version, public_key_pem=pem, algorithm=algorithm)
            .on_conflict_do_nothing(index_elements=["key_version"])
        )
        await db.execute(stmt)
        log.info("evidence.pubkey_archived", key_version=key_version)
    except Exception as exc:  # noqa: BLE001
        log.warning("evidence.pubkey_archive_error", error=str(exc), key_version=key_version)


# ── Write-time sealing ───────────────────────────────────────────────────────


async def seal_operation(
    db: AsyncSession,
    operation: object,  # Operation model instance (avoids circular import)
    *,
    vault_addr: str | None = None,
    vault_token: str | None = None,
    vault_key: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """Seal a completed operation at write-time: chain hash + asymmetric signature.

    Call this immediately after setting an operation's terminal status
    (completed / approved / rejected) and ``completed_at``, within the same
    transaction, so the persisted evidence reflects the event as it occurred.

    Sets on ``operation``:
        - ``chain_hash``        (always)
        - ``event_signature``   (when Vault signing succeeds)
        - ``event_signed_at``   (when Vault signing succeeds)
        - ``signing_key_version`` (when Vault signing succeeds)

    Returns a dict describing what was sealed (for logging/tests).
    """
    op = operation
    prev_hash = await get_latest_chain_hash(db, op.tenant_id)  # type: ignore[attr-defined]

    op_hash = compute_operation_hash(
        operation_id=op.id,  # type: ignore[attr-defined]
        trace_id=op.trace_id,  # type: ignore[attr-defined]
        actor_id=op.actor_id,  # type: ignore[attr-defined]
        artifact_digest=op.artifact_digest,  # type: ignore[attr-defined]
        status=op.status,  # type: ignore[attr-defined]
        created_at=op.created_at,  # type: ignore[attr-defined]
    )
    chain_hash = compute_chain_hash(prev_hash, op_hash)
    op.chain_hash = chain_hash  # type: ignore[attr-defined]

    signature: str | None = None
    key_version: int | None = None
    if vault_addr and vault_token and vault_key:
        signature, key_version = await sign_operation_hash(
            op_hash,
            vault_addr=vault_addr,
            vault_token=vault_token,
            vault_key=vault_key,
            http_client=http_client,
        )
        if signature is not None:
            op.event_signature = signature  # type: ignore[attr-defined]
            op.event_signed_at = datetime.now(UTC)  # type: ignore[attr-defined]
            op.signing_key_version = key_version  # type: ignore[attr-defined]
            # F8-2 (ADR-015): archive the public key for this version so the
            # signature stays verifiable offline, forever, without Vault.
            if key_version is not None:
                await archive_public_key_if_needed(
                    db,
                    key_version,
                    vault_addr=vault_addr,
                    vault_token=vault_token,
                    vault_key=vault_key,
                    http_client=http_client,
                )

    log.info(
        "evidence.sealed",
        operation_id=str(op.id),  # type: ignore[attr-defined]
        chain_hash=chain_hash[:16] + "...",
        signed=signature is not None,
        key_version=key_version,
    )

    return {
        "operation_hash": op_hash,
        "chain_hash": chain_hash,
        "signed": signature is not None,
        "key_version": key_version,
    }
