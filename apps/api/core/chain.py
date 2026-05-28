"""Cryptographic chain hash for operation audit trail (F6-B2).

Each completed operation gets:
    chain_hash = SHA256(prev_chain_hash || operation_hash)

where operation_hash = SHA256(id + trace_id + actor_id + artifact_digest + status + created_at)

This forms a lightweight hash chain (similar to blockchain) that enables:
- Detection of record tampering
- Detection of deleted records (gap in chain)
- Proof of ordering

The chain is per-tenant: each tenant has its own independent chain.
"""
from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# F7-5: the pure chain primitives now live in the shared ``db.evidence`` module
# so the worker (which cannot import ``core.*``) and the API verifier share a
# single source of truth. They are re-exported here for backward compatibility
# with existing ``from core.chain import ...`` call sites.
from db.evidence import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_operation_hash,
    get_latest_chain_hash,
    seal_operation,
)

log = structlog.get_logger(__name__)

__all__ = [
    "GENESIS_HASH",
    "compute_chain_hash",
    "compute_operation_hash",
    "get_latest_chain_hash",
    "compute_and_set_chain_hash",
    "seal_operation",
    "seal_operation_with_settings",
    "verify_chain",
]


async def seal_operation_with_settings(
    db: AsyncSession,
    operation: object,  # Operation model instance
    http_client: object | None = None,
) -> dict:
    """Seal a completed operation using the API's Vault settings (F7-5).

    Convenience wrapper for API-side write-time completion points (review,
    MCP approvals) so they don't each have to thread Vault config. The worker
    uses its own ``WorkerSettings`` and calls ``seal_operation`` directly.
    """
    from config import settings

    sign = settings.audit_sign_on_write
    return await seal_operation(
        db,
        operation,
        vault_addr=settings.vault_addr if sign else None,
        vault_token=settings.vault_dev_token if sign else None,
        vault_key=settings.vault_transit_key if sign else None,
        http_client=http_client,  # type: ignore[arg-type]
    )


async def compute_and_set_chain_hash(
    db: AsyncSession,
    operation: object,  # Operation model instance
) -> str:
    """Compute and set the chain_hash for an operation (chain only, no signature).

    Thin wrapper over ``db.evidence.seal_operation`` kept for backward
    compatibility. New write-time call sites should call ``seal_operation``
    directly so they can also persist the asymmetric signature.
    """
    result = await seal_operation(db, operation)
    return result["chain_hash"]


async def verify_chain(
    db: AsyncSession,
    tenant_id: UUID,
    limit: int = 1000,
) -> dict:
    """Verify the integrity of the chain for a tenant.

    Returns a dict with:
        valid: bool — whether the chain is intact
        checked: int — number of operations checked
        first_broken_at: str | None — operation ID where chain breaks
        gaps: list[str] — operation IDs with missing chain_hash
    """
    from db.models.operation import Operation

    result = await db.execute(
        select(Operation)
        .where(Operation.tenant_id == tenant_id)
        .order_by(Operation.created_at.asc())
        .limit(limit)
    )
    operations = result.scalars().all()

    if not operations:
        return {"valid": True, "checked": 0, "first_broken_at": None, "gaps": []}

    gaps: list[str] = []
    first_broken_at: str | None = None
    prev_hash = GENESIS_HASH
    checked = 0

    for op in operations:
        if op.chain_hash is None:
            gaps.append(str(op.id))
            continue

        checked += 1
        expected_op_hash = compute_operation_hash(
            operation_id=op.id,
            trace_id=op.trace_id,
            actor_id=op.actor_id,
            artifact_digest=op.artifact_digest,
            status=op.status,
            created_at=op.created_at,
        )
        expected_chain_hash = compute_chain_hash(prev_hash, expected_op_hash)

        if op.chain_hash != expected_chain_hash:
            if first_broken_at is None:
                first_broken_at = str(op.id)
            break

        prev_hash = op.chain_hash

    return {
        "valid": first_broken_at is None,
        "checked": checked,
        "first_broken_at": first_broken_at,
        "gaps": gaps,
    }
