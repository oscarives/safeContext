"""auditor_agent — Dramatiq worker that archives artifacts to MinIO (WORM).

Pipeline position: 3rd and final stage.
  process_sanitize → process_audit → operation.status = 'completed'

WORM semantics (ADR-008):
  Original document is uploaded once to MinIO with key:
    artifacts/{operation_id}/original

  Digest is recorded in the artifacts table with worm_locked=True.
  Objects are never overwritten or deleted by application code.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

import dramatiq

from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS

logger = logging.getLogger(__name__)


@dramatiq.actor(
    queue_name="safecontext_audit",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_audit(operation_id: str) -> None:
    asyncio.run(_process_audit_async(operation_id))


async def _process_audit_async(operation_id: str) -> None:
    from sqlalchemy import select, update
    from sqlalchemy.sql import func

    from workers.db import get_session
    from workers.adapters.s3_storage import S3StorageAdapter

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))

    from db.models.operation import Operation
    from db.models.artifact import Artifact
    from db.models.outbox import Outbox

    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="auditor").time():
        # ── Build storage adapter from env ───────────────────────────────────
        storage = S3StorageAdapter(
            endpoint_url=os.environ.get("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.environ.get("MINIO_BUCKET_ARTIFACTS", "safecontext-artifacts"),
            use_ssl=os.environ.get("MINIO_USE_SSL", "false").lower() == "true",
        )

        async with get_session() as session:
            # ── Idempotency: check if artifact already exists ─────────────────
            existing = await session.execute(
                select(Artifact).where(
                    Artifact.operation_id == op_uuid,
                    Artifact.artifact_type == "original",
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                logger.info(
                    "auditor_agent.skip_idempotent id=%s", operation_id
                )
                TASKS_TOTAL.labels(agent="auditor", status="skipped").inc()
                return

            # ── Fetch operation ───────────────────────────────────────────────
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("auditor_agent.operation_not_found id=%s", operation_id)
                TASKS_TOTAL.labels(agent="auditor", status="failure").inc()
                return

            # ── Fetch document from outbox payload ────────────────────────────
            outbox_result = await session.execute(
                select(Outbox).where(
                    Outbox.payload["operation_id"].as_string() == operation_id
                )
            )
            outbox_entry: Outbox | None = outbox_result.scalars().first()

            document_text: str = ""
            if outbox_entry:
                document_text = outbox_entry.payload.get("document_text", "")

            document_bytes: bytes = document_text.encode("utf-8")

            # ── Upload to MinIO (WORM) ────────────────────────────────────────
            minio_key = f"artifacts/{operation_id}/original"
            try:
                digest = await storage.put(
                    key=minio_key,
                    data=document_bytes,
                    metadata={
                        "operation_id": operation_id,
                        "policy_version": operation.policy_version,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "auditor_agent.storage_error id=%s error=%s", operation_id, exc
                )
                TASKS_TOTAL.labels(agent="auditor", status="failure").inc()
                raise

            # ── Persist artifact record ───────────────────────────────────────
            artifact = Artifact(
                operation_id=op_uuid,
                artifact_type="original",
                minio_key=minio_key,
                digest=digest,
                worm_locked=True,
            )
            session.add(artifact)

            # ── Mark operation as completed ───────────────────────────────────
            await session.execute(
                update(Operation)
                .where(Operation.id == op_uuid)
                .values(
                    status="completed",
                    completed_at=func.now(),
                )
            )

            logger.info(
                "auditor_agent.done id=%s digest=%s key=%s",
                operation_id,
                digest,
                minio_key,
            )

    TASKS_TOTAL.labels(agent="auditor", status="success").inc()
