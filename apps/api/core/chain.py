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

import hashlib
import json
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Genesis hash — used as prev_chain_hash for the first operation in a chain
GENESIS_HASH = "0" * 64


def compute_operation_hash(
    operation_id: UUID,
    trace_id: UUID,
    actor_id: UUID,
    artifact_digest: str,
    status: str,
    created_at: datetime,
) -> str:
    """Compute the content hash of an individual operation."""
    content = json.dumps({
        "id": str(operation_id),
        "trace_id": str(trace_id),
        "actor_id": str(actor_id),
        "artifact_digest": artifact_digest,
        "status": status,
        "created_at": created_at.isoformat() if created_at else "",
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def compute_chain_hash(prev_chain_hash: str, operation_hash: str) -> str:
    """Compute chain_hash = SHA256(prev_chain_hash || operation_hash)."""
    combined = f"{prev_chain_hash}{operation_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()


async def get_latest_chain_hash(
    db: AsyncSession,
    tenant_id: UUID,
) -> str:
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


async def compute_and_set_chain_hash(
    db: AsyncSession,
    operation: object,  # Operation model instance
) -> str:
    """Compute and set the chain_hash for an operation.

    Call this when an operation is completed (status changes to completed/approved/rejected).
    """
    op = operation  # type alias for readability
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

    log.info(
        "chain.hash_computed",
        operation_id=str(op.id),  # type: ignore[attr-defined]
        chain_hash=chain_hash[:16] + "...",
    )

    return chain_hash


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
