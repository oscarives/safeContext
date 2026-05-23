import hashlib
import time
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.auth_oidc import _decode_token
from core.constants import SENTINEL_ACTOR_ID
from db.models.operation import Operation as OperationModel
from core.logging import get_logger
from core.metrics import operations_total, scan_duration
from core.tracing import get_trace_id, tracer
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.session import get_db
from schemas.scan import ScanRequest, ScanResponse

router = APIRouter()
logger = get_logger(__name__)

_FALLBACK_POLICY_VERSION = "1.0.0"


async def _get_policy_version(policy_name: str, client: httpx.AsyncClient) -> str:
    """Query OPA for the current policy version; fall back gracefully on transient errors."""
    try:
        url = f"{settings.opa_url}/v1/data/safecontext/policy/policy_version"
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            version = data.get("result", _FALLBACK_POLICY_VERSION)
            return str(version)
        logger.warning("scan.opa_version.http_error", status=resp.status_code)
    except httpx.TimeoutException:
        logger.warning("scan.opa_version.timeout", policy_name=policy_name)
    except httpx.ConnectError:
        logger.warning("scan.opa_version.connect_error", policy_name=policy_name)
    except Exception as exc:
        logger.error("scan.opa_version.unexpected_error", error=str(exc))
    return _FALLBACK_POLICY_VERSION


async def _resolve_scan_actor(request: Request) -> tuple[uuid.UUID, str]:
    """Resolve actor_id and actor_type from the Authorization header.

    Accepts two authentication mechanisms:
    - MCP agent token (static secret = settings.mcp_auth_token) → sentinel actor, "mcp_agent"
    - Keycloak JWT (from the web UI) → actor_id = uuid(sub claim), "human"

    This replaces the hardcoded SENTINEL_ACTOR_ID so that scans made from the
    web UI are correctly attributed to the authenticated user (TECH-DEBT-001).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header[7:]

    # MCP agent token — static secret, not a JWT
    if token == settings.mcp_auth_token:
        return SENTINEL_ACTOR_ID, "mcp_agent"

    # Keycloak JWT — decode and extract the sub claim
    try:
        payload = await _decode_token(token)
        sub = payload.get("sub", "")
        if not sub:
            raise ValueError("empty sub claim in JWT")
        return uuid.UUID(sub), "human"
    except HTTPException:
        raise  # re-raise 401 from _decode_token
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


@router.post("/scan", response_model=ScanResponse, tags=["scan"])
async def scan(
    request: Request,
    body: ScanRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanResponse:
    """
    Accept a document and enqueue it for asynchronous PII scanning.

    Accepts both MCP agent tokens and Keycloak JWTs (web UI).
    Returns a ScanResponse immediately with trace_id and artifact_digest.
    Findings are populated asynchronously by workers.
    """
    with tracer.start_as_current_span("scan") as span:
        trace_id_hex = get_trace_id()

        try:
            trace_uuid = uuid.UUID(trace_id_hex)
        except ValueError:
            trace_uuid = uuid.uuid4()

        span.set_attribute("safecontext.trace_id", str(trace_uuid))
        span.set_attribute("safecontext.policy_name", body.policy_name)

        t_start = time.perf_counter()

        # --- resolve actor from Authorization header (MCP token OR Keycloak JWT) ---
        actor_id, actor_type = await _resolve_scan_actor(request)

        # --- artifact digest ---
        artifact_digest = hashlib.sha256(body.document.encode()).hexdigest()

        # --- policy version (resolve before dedup so lookup uses real value) ---
        http_client: httpx.AsyncClient = request.app.state.http_client
        policy_version = body.policy_version or await _get_policy_version(
            body.policy_name, http_client
        )

        # --- deduplication: return previous result for identical documents ------
        # If the same document + policy combination was already successfully
        # processed, return the existing trace_id immediately without re-scanning.
        from sqlalchemy import select as sa_select
        existing_op = (await db.execute(
            sa_select(OperationModel)
            .where(
                OperationModel.artifact_digest == artifact_digest,
                OperationModel.policy_version == policy_version,
                OperationModel.status.in_(["completed", "escalated"]),
            )
            .order_by(OperationModel.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if existing_op is not None:
            logger.info(
                "scan.deduplicated",
                artifact_digest=artifact_digest,
                reusing_trace_id=str(existing_op.trace_id),
            )
            response.headers["X-Trace-ID"] = str(existing_op.trace_id)
            return ScanResponse(
                trace_id=existing_op.trace_id,
                artifact_digest=artifact_digest,
                policy_version=existing_op.policy_version,
                findings=[],
                requires_human_review=existing_op.status == "escalated",
            )

        # --- outbox pattern: single transaction ---
        operation_id = uuid.uuid4()
        document_id = uuid.uuid4()

        operation = Operation(
            id=operation_id,
            trace_id=trace_uuid,
            actor_id=actor_id,
            actor_type=actor_type,
            document_id=document_id,
            artifact_digest=artifact_digest,
            policy_version=policy_version,
            status="pending",
        )
        outbox_event = Outbox(
            event_type="scan_requested",
            payload={
                "operation_id": str(operation_id),
                "document_text": body.document,
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
            actor_id=str(actor_id),
            actor_type=actor_type,
            artifact_digest=artifact_digest,
            policy_name=body.policy_name,
            elapsed_s=round(elapsed, 4),
        )

        response.headers["X-Trace-ID"] = str(trace_uuid)

        return ScanResponse(
            trace_id=trace_uuid,
            artifact_digest=artifact_digest,
            policy_version=policy_version,
            findings=[],
            requires_human_review=False,
        )
