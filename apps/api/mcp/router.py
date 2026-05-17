"""MCP Server — FastAPI router that exposes SafeContext agents as MCP tools.

All tools share authentication (Bearer token) and audit trail (actor_type='mcp_agent').
Tool schemas are versioned from F1; clients can pin tool_version from F4.
"""
import hashlib
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.tracing import get_trace_id, tracer
from db.models.operation import Operation
from db.models.outbox import Outbox
from db.models.redaction import Redaction
from db.session import get_db
from mcp.auth import require_mcp_token
from mcp.schemas import (
    ClassifyToolRequest,
    ClassifyToolResponse,
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


# ── Tool discovery ────────────────────────────────────────────────────────────

@router.get("/tools", summary="List available MCP tools and their schemas")
async def list_tools(
    _token: Annotated[str, Depends(require_mcp_token)],
) -> dict[str, Any]:
    return {"tools": MCP_TOOLS}


# ── safecontext.scan ──────────────────────────────────────────────────────────

@router.post(
    "/tools/safecontext.scan",
    response_model=MCPToolResult,
    summary="Scan document for PII, secrets and sensitive data",
)
async def tool_scan(
    request: ScanToolRequest,
    response: Response,
    _token: Annotated[str, Depends(require_mcp_token)],
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

        # actor_type='mcp_agent' — ADR-004, E1.4 acceptance criterion
        operation = Operation(
            trace_id=trace_uuid,
            actor_id=uuid.uuid4(),  # replaced by real agent identity in F4
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
                "document": request.document,
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
    _token: Annotated[str, Depends(require_mcp_token)],
    db: AsyncSession = Depends(get_db),
) -> MCPToolResult:
    with tracer.start_as_current_span("mcp.sanitize"):
        # Retrieve operation by trace_id to get document content
        from sqlalchemy import select
        result = await db.execute(
            select(Operation).where(Operation.trace_id == request.trace_id)
        )
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
        document = outbox_entry.payload.get("document", "") if outbox_entry else ""

        # Apply redactions
        redaction_map = []
        sanitized = document
        offset = 0
        for f in sorted(findings, key=lambda x: x.span_start):
            start = f.span_start + offset
            end = f.span_end + offset
            if request.redaction_type == "mask":
                replacement = "[REDACTED]"
            elif request.redaction_type == "remove":
                replacement = ""
            else:
                replacement = request.replacement_token or "[REDACTED]"

            sanitized = sanitized[:start] + replacement + sanitized[end:]
            offset += len(replacement) - (f.span_end - f.span_start)

            redaction_map.append({
                "finding_id": str(f.id),
                "span_start": f.span_start,
                "span_end": f.span_end,
                "redaction_type": request.redaction_type,
                "policy_version": operation.policy_version,
            })

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
    _token: Annotated[str, Depends(require_mcp_token)],
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
            if any(k in lower for k in ["password", "secret", "api_key", "token", "ssn", "credit card"]):
                level = "restricted"
                justification = "Contains credential or highly sensitive data pattern"
            elif any(k in lower for k in ["confidential", "internal only", "do not share", "pii", "personal"]):
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

            sections.append(SectionClassification(
                section_id=idx,
                level=level,
                justification=justification,
            ))

        # Record operation for audit trail
        operation = Operation(
            trace_id=trace_uuid,
            actor_id=uuid.uuid4(),
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
    _token: Annotated[str, Depends(require_mcp_token)],
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
    _token: Annotated[str, Depends(require_mcp_token)],
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
        vr = await client.get(
            f"{settings.opa_url}/v1/data/safecontext/policy/policy_version"
        )
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
