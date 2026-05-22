"""sanitizer_agent — Dramatiq worker that redacts detected spans.

Pipeline position: 2nd stage.
  process_scan → process_sanitize → process_audit

Idempotency guarantee:
  Checks whether redactions already exist for this operation before writing.
  Re-delivery is therefore safe — existing redactions are not duplicated.
"""

from __future__ import annotations

import asyncio
import uuid

import dramatiq
import structlog
from sqlalchemy import select, update

from db.models.finding import Finding as FindingModel
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.models.redaction import Redaction

from workers.core.db import get_session
from workers.core.metrics import TASKS_TOTAL, TASK_DURATION_SECONDS

logger = structlog.get_logger(__name__)


@dramatiq.actor(
    queue_name="safecontext_sanitize",
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def process_sanitize(operation_id: str) -> None:
    asyncio.run(_process_sanitize_async(operation_id))


def _apply_redactions(text: str, findings: list, redaction_map: dict[uuid.UUID, str]) -> str:
    """Apply span-based redactions to the document text.

    Processes spans from end to start so that earlier span offsets remain valid
    after each replacement. The result is a coherent sanitized document where
    every sensitive span is replaced by its redaction marker.

    Args:
        text:          Original document text.
        findings:      List of FindingModel instances ordered by span_start.
        redaction_map: Mapping of finding.id → redaction_type.

    Returns:
        The sanitized text with all PII/secret spans replaced.
    """
    _REDACTION_MARKERS = {
        "mask":    "[REDACTED]",
        "remove":  "",
        "replace": "[REDACTED]",
    }

    # Sort descending by span_start so we process from the end of the string
    # — this preserves the byte offsets of earlier spans during replacement.
    sorted_findings = sorted(findings, key=lambda f: f.span_start, reverse=True)

    chars = list(text)
    for f in sorted_findings:
        marker = _REDACTION_MARKERS.get(redaction_map.get(f.id, "mask"), "[REDACTED]")
        chars[f.span_start:f.span_end] = list(marker)

    return "".join(chars)


async def _process_sanitize_async(operation_id: str) -> None:
    op_uuid = uuid.UUID(operation_id)

    with TASK_DURATION_SECONDS.labels(agent="sanitizer").time():
        async with get_session() as session:
            # ── Idempotency check ────────────────────────────────────────────
            existing = await session.execute(
                select(Redaction).where(Redaction.operation_id == op_uuid).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                logger.info("sanitizer_agent.skip_idempotent", id=operation_id)
                TASKS_TOTAL.labels(agent="sanitizer", status="skipped").inc()
                return

            # ── Fetch operation and its findings ─────────────────────────────
            op_result = await session.execute(
                select(Operation).where(Operation.id == op_uuid)
            )
            operation: Operation | None = op_result.scalar_one_or_none()

            if operation is None:
                logger.error("sanitizer_agent.operation_not_found", id=operation_id)
                TASKS_TOTAL.labels(agent="sanitizer", status="failure").inc()
                return

            findings_result = await session.execute(
                select(FindingModel).where(FindingModel.operation_id == op_uuid)
            )
            findings = findings_result.scalars().all()

            # ── Fetch original document text from outbox payload ──────────────
            outbox_result = await session.execute(
                select(Outbox).where(
                    Outbox.payload["operation_id"].as_string() == operation_id
                )
            )
            outbox_entry: Outbox | None = outbox_result.scalars().first()
            document_text: str = outbox_entry.payload.get("document_text", "") if outbox_entry else ""

            # ── Apply redactions and compute sanitized text ───────────────────
            redaction_map: dict[uuid.UUID, str] = {}

            if not findings:
                logger.info(
                    "sanitizer_agent.no_findings",
                    id=operation_id,
                    proceeding_to="audit",
                )
                sanitized_text = document_text  # no changes needed
            else:
                for f in findings:
                    redaction_type = _severity_to_redaction_type(f.severity)
                    redaction_map[f.id] = redaction_type
                    redaction = Redaction(
                        finding_id=f.id,
                        operation_id=op_uuid,
                        redaction_type=redaction_type,
                        policy_version=operation.policy_version,
                    )
                    session.add(redaction)
                    logger.debug(
                        "sanitizer_agent.redaction",
                        finding_id=str(f.id),
                        type=redaction_type,
                    )

                # Build the sanitized text by applying all redactions
                sanitized_text = _apply_redactions(document_text, findings, redaction_map)

            # ── Persist sanitized text on the operation ───────────────────────
            await session.execute(
                update(Operation)
                .where(Operation.id == op_uuid)
                .values(sanitized_text=sanitized_text)
            )

            logger.info(
                "sanitizer_agent.done",
                id=operation_id,
                redactions=len(findings),
                sanitized_length=len(sanitized_text),
            )

    from workers.agents.auditor_agent import process_audit
    process_audit.send(operation_id)
    logger.info("sanitizer_agent.enqueued_audit", id=operation_id)
    TASKS_TOTAL.labels(agent="sanitizer", status="success").inc()


def _severity_to_redaction_type(severity: str) -> str:
    """Map finding severity to redaction strategy."""
    return {
        "critical": "mask",
        "high": "mask",
        "medium": "mask",
        "low": "replace",
    }.get(severity, "mask")
