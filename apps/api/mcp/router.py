"""MCP Server — FastAPI router that exposes SafeContext agents as MCP tools.

All tools share authentication (Bearer token) and audit trail (actor_type='mcp_agent').
Tool schemas are versioned from F1; clients can pin tool_version from F4.
"""

import hashlib
import uuid
from datetime import UTC
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_oidc import check_rate_limit, check_rate_limit_redis
from core.tracing import get_trace_id, tracer
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.models.redaction import Redaction
from db.session import get_db
from mcp.auth import require_mcp_oauth, require_mcp_token  # noqa: F401 — keep alias for imports
from mcp.scopes import require_tool_scope
from mcp.schemas import (
    ClassifyToolRequest,
    ClassifyToolResponse,
    MCPToolCallVersioned,
    MCPToolResult,
    SanitizeToolRequest,
    SanitizeToolResponse,
    ScanToolRequest,
    ScanToolResponse,
    SectionClassification,
)
from mcp.tools import MCP_TOOLS

log = structlog.get_logger()
router = APIRouter(prefix="/v1/mcp", tags=["mcp"])

_LEVEL_ORDER = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
_SEVERITY_TO_LEVEL = {
    "critical": "restricted",
    "high": "confidential",
    "medium": "internal",
    "low": "public",
}


# ── Version registry (E4.5) ───────────────────────────────────────────────────

SUPPORTED_VERSIONS = {"1.0.0", "1.1.0"}
CURRENT_VERSION = "1.1.0"

# Version compatibility matrix: maps (tool, requested_version) → handler name.
# N-1 compatibility: 1.0.0 requests are handled by current handlers.
VERSION_COMPAT: dict[tuple[str, str], str] = {
    ("safecontext.scan", "1.0.0"): "tool_scan",
    ("safecontext.scan", "1.1.0"): "tool_scan",
    ("safecontext.sanitize", "1.0.0"): "tool_sanitize",
    ("safecontext.sanitize", "1.1.0"): "tool_sanitize",
    ("safecontext.classify", "1.0.0"): "tool_classify",
    ("safecontext.classify", "1.1.0"): "tool_classify",
    ("safecontext.audit", "1.0.0"): "tool_audit",
    ("safecontext.audit", "1.1.0"): "tool_audit",
    ("safecontext.policy.get", "1.0.0"): "tool_policy_get",
    ("safecontext.policy.get", "1.1.0"): "tool_policy_get",
    ("safecontext.approve", "1.1.0"): "tool_approve",  # new in 1.1.0
}


# ── Tool discovery ────────────────────────────────────────────────────────────


@router.get("/tools", summary="List available MCP tools and their schemas")
async def list_tools(
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    request: Request,
) -> dict[str, Any]:
    fallback = request.client.host if request.client else "unknown"
    client_id = request.headers.get("X-Client-ID", fallback)
    try:
        await check_rate_limit_redis(client_id, request.app.state.redis_rl)
    except Exception:
        check_rate_limit(client_id)  # fallback to in-memory if Redis unavailable
    return {"tools": MCP_TOOLS}


# ── Versioned dispatch (E4.5) ─────────────────────────────────────────────────


@router.post("/call", response_model=MCPToolResult, summary="Versioned MCP tool dispatch")
async def dispatch_tool(
    call: MCPToolCallVersioned,
    response: Response,
    request: Request,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    fallback = request.client.host if request.client else "unknown"
    client_id = request.headers.get("X-Client-ID", fallback)
    try:
        await check_rate_limit_redis(client_id, request.app.state.redis_rl)
    except Exception:
        check_rate_limit(client_id)  # fallback to in-memory if Redis unavailable
    version = call.tool_version
    if version not in SUPPORTED_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported tool version '{version}'. Supported: {sorted(SUPPORTED_VERSIONS)}",
        )

    key = (call.tool, version)
    if key not in VERSION_COMPAT:
        # Try current version as fallback for unknown combos
        key = (call.tool, CURRENT_VERSION)
    if key not in VERSION_COMPAT:
        raise HTTPException(status_code=404, detail=f"Tool '{call.tool}' not found")

    # T9: enforce consent-management scope before dispatching
    require_tool_scope(call.tool, _token_payload)

    if call.tool == "safecontext.scan":
        req = ScanToolRequest(**call.input)
        return await tool_scan(req, response, _token_payload, db)
    elif call.tool == "safecontext.sanitize":
        req = SanitizeToolRequest(**call.input)
        return await tool_sanitize(req, response, _token_payload, db)
    elif call.tool == "safecontext.classify":
        req = ClassifyToolRequest(**call.input)
        return await tool_classify(req, response, _token_payload, db)
    elif call.tool == "safecontext.approve":
        if version == "1.0.0":
            raise HTTPException(400, "safecontext.approve requires tool_version >= 1.1.0")
        req = ApproveToolRequest(**call.input)
        return await tool_approve(req, response, _token_payload, db)
    else:
        raise HTTPException(404, f"Tool '{call.tool}' not supported via /call")


# ── safecontext.scan ──────────────────────────────────────────────────────────


@router.post(
    "/tools/safecontext.scan",
    response_model=MCPToolResult,
    summary="Scan document for PII, secrets and sensitive data",
)
async def tool_scan(
    request: ScanToolRequest,
    response: Response,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    with tracer.start_as_current_span("mcp.scan") as span:
        artifact_digest = hashlib.sha256(request.document.encode()).hexdigest()
        span.set_attribute("artifact.digest", artifact_digest)

        trace_id_hex = get_trace_id()
        try:
            trace_uuid = uuid.UUID(trace_id_hex)
        except ValueError:
            trace_uuid = uuid.uuid4()

        # Derive actor_id from JWT sub claim (or raw token in dev mode for compat)
        _actor_token = _token_payload.get("_raw_token") or _token_payload.get("sub", "unknown")
        # actor_type='mcp_agent' — ADR-004, E1.4 acceptance criterion
        operation = Operation(
            trace_id=trace_uuid,
            actor_id=uuid.UUID(hashlib.sha256(_actor_token.encode()).hexdigest()[:32]),
            actor_type="mcp_agent",
            document_id=uuid.uuid4(),
            artifact_digest=artifact_digest,
            policy_version=request.policy_version or "1.0.0",
            status="pending",
        )
        outbox_event = Outbox(
            event_type="scan_requested",
            payload={
                "operation_id": str(operation.id),
                "document_text": request.document,  # workers read this key
                "document_hash": artifact_digest,
                "policy_name": request.policy_name,
                "source": "mcp",
            },
        )

        try:
            async with db.begin():
                db.add(operation)
                db.add(outbox_event)
        except Exception as exc:
            log.error("mcp.scan.db_error", trace_id=str(trace_uuid), error=str(exc))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exc

        response.headers["X-Trace-ID"] = str(trace_uuid)
        log.info("mcp.scan.enqueued", trace_id=str(trace_uuid), actor_type="mcp_agent")

        scan_result = ScanToolResponse(
            trace_id=trace_uuid,
            artifact_digest=artifact_digest,
            policy_version=operation.policy_version,
            findings=[],
            requires_human_review=False,
        )
        return MCPToolResult(
            tool="safecontext.scan",
            version="1.0.0",
            output=scan_result.model_dump(mode="json"),
            trace_id=str(trace_uuid),
        )


# ── safecontext.sanitize ─────────────────────────────────────────────────────


@router.post(
    "/tools/safecontext.sanitize",
    response_model=MCPToolResult,
    summary="Sanitize document based on prior scan findings",
)
async def tool_sanitize(
    request: SanitizeToolRequest,
    response: Response,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    with tracer.start_as_current_span("mcp.sanitize"):
        # Retrieve operation by trace_id to get document content
        from sqlalchemy import select

        result = await db.execute(select(Operation).where(Operation.trace_id == request.trace_id))
        operation = result.scalar_one_or_none()
        if operation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No operation found for trace_id {request.trace_id}",
            )
        if operation.status == "escalated":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Operation requires human review before sanitization",
            )

        # Retrieve findings to build redaction map
        from db.models.finding import Finding

        findings_result = await db.execute(
            select(Finding).where(Finding.operation_id == operation.id)
        )
        findings = findings_result.scalars().all()

        # Retrieve original document from outbox payload
        from db.models.outbox import Outbox as OutboxModel

        outbox_result = await db.execute(
            select(OutboxModel).where(
                OutboxModel.payload["operation_id"].as_string() == str(operation.id)
            )
        )
        outbox_entry = outbox_result.scalar_one_or_none()
        if not outbox_entry or not outbox_entry.payload.get("document_text"):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Original document not found; it may have been archived or deleted",
            )
        document = outbox_entry.payload["document_text"]

        # Apply redactions right-to-left to avoid offset shift issues.
        # Merge overlapping spans first to prevent double-redaction.
        sorted_findings = sorted(findings, key=lambda x: (x.span_start, x.span_end))
        merged: list[tuple[int, int, list]] = []
        for f in sorted_findings:
            if merged and f.span_start < merged[-1][1]:
                prev_start, prev_end, prev_fs = merged[-1]
                merged[-1] = (prev_start, max(prev_end, f.span_end), prev_fs + [f])
            else:
                merged.append((f.span_start, f.span_end, [f]))

        if request.redaction_type == "mask":
            replacement = "[REDACTED]"
        elif request.redaction_type == "remove":
            replacement = ""
        else:
            replacement = request.replacement_token or "[REDACTED]"

        redaction_map = []
        sanitized = document
        for start, end, group in reversed(merged):
            sanitized = sanitized[:start] + replacement + sanitized[end:]
            for f in group:
                redaction_map.append(
                    {
                        "finding_id": str(f.id),
                        "span_start": f.span_start,
                        "span_end": f.span_end,
                        "redaction_type": request.redaction_type,
                        "policy_version": operation.policy_version,
                    }
                )
        redaction_map.reverse()

        sanitized_digest = hashlib.sha256(sanitized.encode()).hexdigest()
        response.headers["X-Trace-ID"] = str(request.trace_id)

        sanitize_result = SanitizeToolResponse(
            trace_id=request.trace_id,
            sanitized_document=sanitized,
            sanitized_artifact_digest=sanitized_digest,
            redaction_map=redaction_map,
        )
        return MCPToolResult(
            tool="safecontext.sanitize",
            version="1.0.0",
            output=sanitize_result.model_dump(mode="json"),
            trace_id=str(request.trace_id),
        )


# ── safecontext.classify ─────────────────────────────────────────────────────


@router.post(
    "/tools/safecontext.classify",
    response_model=MCPToolResult,
    summary="Classify document sensitivity level by section",
)
async def tool_classify(
    request: ClassifyToolRequest,
    response: Response,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    with tracer.start_as_current_span("mcp.classify") as span:
        trace_uuid = uuid.uuid4()
        span.set_attribute("safecontext.trace_id", str(trace_uuid))

        # Split document into sections (paragraphs)
        paragraphs = [p.strip() for p in request.document.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [request.document]

        # Classify each section based on keyword heuristics + length
        # Real classification runs via process_classify worker (async)
        sections: list[SectionClassification] = []
        max_level = "public"

        for idx, para in enumerate(paragraphs):
            lower = para.lower()
            credential_keys = ["password", "secret", "api_key", "token", "ssn", "credit card"]
            confidential_keys = ["confidential", "internal only", "do not share", "pii", "personal"]
            if any(k in lower for k in credential_keys):
                level = "restricted"
                justification = "Contains credential or highly sensitive data pattern"
            elif any(k in lower for k in confidential_keys):
                level = "confidential"
                justification = "Contains confidential or personal information markers"
            elif any(k in lower for k in ["internal", "draft", "not for distribution"]):
                level = "internal"
                justification = "Marked as internal use"
            else:
                level = "public"
                justification = "No sensitive markers detected"

            if _LEVEL_ORDER[level] > _LEVEL_ORDER[max_level]:
                max_level = level

            sections.append(
                SectionClassification(
                    section_id=idx,
                    level=level,
                    justification=justification,
                )
            )

        # Derive actor_id from JWT sub claim (or raw token in dev mode for compat)
        _actor_token = _token_payload.get("_raw_token") or _token_payload.get("sub", "unknown")
        # Record operation for audit trail
        operation = Operation(
            trace_id=trace_uuid,
            actor_id=uuid.UUID(hashlib.sha256(_actor_token.encode()).hexdigest()[:32]),
            actor_type="mcp_agent",
            document_id=uuid.uuid4(),
            artifact_digest=hashlib.sha256(request.document.encode()).hexdigest(),
            policy_version="1.0.0",
            status="completed",
        )
        async with db.begin():
            db.add(operation)

        response.headers["X-Trace-ID"] = str(trace_uuid)

        classify_result = ClassifyToolResponse(
            trace_id=trace_uuid,
            overall_level=max_level,
            sections=sections,
        )
        return MCPToolResult(
            tool="safecontext.classify",
            version="1.0.0",
            output=classify_result.model_dump(mode="json"),
            trace_id=str(trace_uuid),
        )


# ── safecontext.audit ────────────────────────────────────────────────────────


class AuditToolRequest(BaseModel):
    trace_id: uuid.UUID


@router.post(
    "/tools/safecontext.audit",
    response_model=MCPToolResult,
    summary="Return full audit evidence for a given trace_id",
)
async def tool_audit(
    request: AuditToolRequest,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    from api.v1.audit import get_audit_export

    result = await get_audit_export(request.trace_id, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No operation for trace_id {request.trace_id}",
        )
    return MCPToolResult(
        tool="safecontext.audit",
        version="1.0.0",
        output=result.model_dump(mode="json"),
        trace_id=str(request.trace_id),
    )


# ── safecontext.policy.get ───────────────────────────────────────────────────


class PolicyGetRequest(BaseModel):
    policy_name: str
    policy_version: str | None = None


@router.post(
    "/tools/safecontext.policy.get",
    response_model=MCPToolResult,
    summary="Return active OPA policy with version",
)
async def tool_policy_get(
    request: PolicyGetRequest,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
) -> MCPToolResult:
    import httpx

    from config import settings

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{settings.opa_url}/v1/data/safecontext/policy")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OPA policy unavailable",
            )
        policy_data = resp.json().get("result", {})

    policy_version: str = "1.0.0"
    async with httpx.AsyncClient(timeout=5.0) as client:
        vr = await client.get(f"{settings.opa_url}/v1/data/safecontext/policy/policy_version")
        if vr.status_code == 200:
            raw = vr.json().get("result", "1.0.0")
            policy_version = str(raw)

    log.info(
        "mcp.policy_get",
        policy_name=request.policy_name,
        policy_version=policy_version,
    )

    return MCPToolResult(
        tool="safecontext.policy.get",
        version="1.0.0",
        output={
            "policy_name": request.policy_name,
            "policy_version": policy_version,
            "policy": policy_data,
        },
    )


# ── safecontext.approve (E4.6) ────────────────────────────────────────────────


class ApproveToolRequest(BaseModel):
    finding_id: uuid.UUID
    decision: Literal["approve", "reject"]
    justification: str
    agent_client_id: str  # identity of the delegated agent


@router.post(
    "/tools/safecontext.approve",
    response_model=MCPToolResult,
    summary="Agent-delegated approval of a finding (requires delegated permission)",
)
async def tool_approve(
    request: ApproveToolRequest,
    response: Response,
    _token_payload: Annotated[dict, Depends(require_mcp_oauth)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    with tracer.start_as_current_span("mcp.approve") as span:
        span.set_attribute("finding.id", str(request.finding_id))
        span.set_attribute("agent.client_id", request.agent_client_id)

        from sqlalchemy import select

        from db.models.finding import Finding

        # Load finding
        result = await db.execute(select(Finding).where(Finding.id == request.finding_id))
        finding = result.scalar_one_or_none()
        if finding is None:
            raise HTTPException(404, f"Finding {request.finding_id} not found")

        # Load operation to verify it's escalated
        result2 = await db.execute(select(Operation).where(Operation.id == finding.operation_id))
        operation = result2.scalar_one_or_none()
        if operation is None or operation.status != "escalated":
            raise HTTPException(409, "Operation is not in escalated state")

        trace_uuid = operation.trace_id

        if request.decision == "approve":
            agent_uuid = uuid.uuid5(uuid.NAMESPACE_URL, request.agent_client_id)
            redaction = Redaction(
                finding_id=finding.id,
                operation_id=operation.id,
                redaction_type="mask",
                policy_version=operation.policy_version,
                approved_by_agent_id=agent_uuid,
            )
            async with db.begin():
                db.add(redaction)
                operation.status = "completed"
                from datetime import datetime

                operation.completed_at = datetime.now(UTC)
        else:
            async with db.begin():
                operation.status = "rejected"
                from datetime import datetime

                operation.completed_at = datetime.now(UTC)

        log.info(
            "mcp.approve.recorded",
            finding_id=str(request.finding_id),
            decision=request.decision,
            agent_client_id=request.agent_client_id,
            trace_id=str(trace_uuid),
        )

        response.headers["X-Trace-ID"] = str(trace_uuid)
        return MCPToolResult(
            tool="safecontext.approve",
            version="1.1.0",
            output={
                "finding_id": str(request.finding_id),
                "decision": request.decision,
                "trace_id": str(trace_uuid),
                "recorded_by": request.agent_client_id,
            },
            trace_id=str(trace_uuid),
        )
