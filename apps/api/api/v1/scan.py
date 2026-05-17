import hashlib
import time
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.logging import get_logger
from core.metrics import operations_total, scan_duration
from core.tracing import get_trace_id, tracer
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.session import get_db
from schemas.scan import ScanRequest, ScanResponse

router = APIRouter()
logger = get_logger(__name__)

_FALLBACK_POLICY_VERSION = "v0.0.0"


async def _get_policy_version(policy_name: str) -> str:
    """Query OPA for the current policy version; fall back gracefully."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"{settings.opa_url}{settings.opa_policy_path}/version"
            resp = await client.get(url, params={"policy": policy_name})
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("result", _FALLBACK_POLICY_VERSION))
    except Exception as exc:
        logger.warning("scan.opa_version.error", error=str(exc))
    return _FALLBACK_POLICY_VERSION


@router.post("/scan", response_model=ScanResponse, tags=["scan"])
async def scan(
    request: Request,
    body: ScanRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanResponse:
    """
    Accept a document and enqueue it for asynchronous PII scanning.

    Returns a ScanResponse immediately with trace_id and artifact_digest.
    Findings are populated asynchronously by workers.
    """
    with tracer.start_as_current_span("scan") as span:
        trace_id_hex = get_trace_id()

        # Derive a stable UUID from the OTel trace_id hex string
        try:
            trace_uuid = uuid.UUID(trace_id_hex)
        except ValueError:
            trace_uuid = uuid.uuid4()

        span.set_attribute("safecontext.trace_id", str(trace_uuid))
        span.set_attribute("safecontext.policy_name", body.policy_name)

        t_start = time.perf_counter()

        # --- artifact digest ---
        artifact_digest = hashlib.sha256(body.document.encode()).hexdigest()

        # --- policy version ---
        policy_version = body.policy_version or await _get_policy_version(body.policy_name)

        # --- outbox pattern: single transaction ---
        operation_id = uuid.uuid4()
        document_id = uuid.uuid4()

        # Use a fixed sentinel actor_id for API-originated requests;
        # real auth middleware will replace this.
        actor_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        operation = Operation(
            id=operation_id,
            trace_id=trace_uuid,
            actor_id=actor_id,
            actor_type="mcp_agent",
            document_id=document_id,
            artifact_digest=artifact_digest,
            policy_version=policy_version,
            status="pending",
        )
        outbox_event = Outbox(
            event_type="scan_requested",
            payload={
                "operation_id": str(operation_id),
                "document_hash": artifact_digest,
                "policy_name": body.policy_name,
                "policy_version": policy_version,
                "document_encoding": body.document_encoding,
            },
            processed=False,
        )

        try:
            db.add(operation)
            db.add(outbox_event)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                "scan.db_commit.error",
                trace_id=str(trace_uuid),
                operation_id=str(operation_id),
                error=str(exc),
            )
            span.record_exception(exc)
            raise HTTPException(status_code=500, detail="Failed to persist scan operation") from exc

        # --- enqueue AFTER commit (outbox guarantee) ---
        broker = request.app.state.broker
        try:
            await broker.enqueue(
                "scan_requests",
                {
                    "operation_id": str(operation_id),
                    "document_hash": artifact_digest,
                    "policy_name": body.policy_name,
                    "policy_version": policy_version,
                },
            )
        except Exception as exc:
            # Non-fatal: outbox relay will pick this up later
            logger.warning(
                "scan.enqueue.error",
                trace_id=str(trace_uuid),
                operation_id=str(operation_id),
                error=str(exc),
            )

        # --- metrics ---
        elapsed = time.perf_counter() - t_start
        scan_duration.labels(policy_name=body.policy_name).observe(elapsed)
        operations_total.labels(status="pending").inc()

        logger.info(
            "scan.created",
            trace_id=str(trace_uuid),
            operation_id=str(operation_id),
            artifact_digest=artifact_digest,
            policy_name=body.policy_name,
            elapsed_s=round(elapsed, 4),
        )

        # --- response ---
        response.headers["X-Trace-ID"] = str(trace_uuid)

        return ScanResponse(
            trace_id=trace_uuid,
            artifact_digest=artifact_digest,
            policy_version=policy_version,
            findings=[],
            requires_human_review=False,
        )
