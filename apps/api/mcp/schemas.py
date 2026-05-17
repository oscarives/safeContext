"""MCP tool request/response schemas — matches DOC-3 formal tool definitions."""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── safecontext.scan ──────────────────────────────────────────────────────────

class ScanToolRequest(BaseModel):
    document: str
    document_encoding: Literal["text", "base64"] = "text"
    policy_name: str
    policy_version: str | None = None


class FindingResult(BaseModel):
    id: UUID
    detector: str
    rule_id: str
    span_start: int
    span_end: int
    confidence: float = Field(ge=0, le=1)
    severity: Literal["low", "medium", "high", "critical"]
    explanation: dict[str, Any]


class ScanToolResponse(BaseModel):
    trace_id: UUID
    artifact_digest: str
    policy_version: str
    findings: list[FindingResult]
    requires_human_review: bool


# ── safecontext.sanitize ──────────────────────────────────────────────────────

class SanitizeToolRequest(BaseModel):
    trace_id: UUID
    redaction_type: Literal["mask", "remove", "replace"]
    replacement_token: str | None = None


class RedactionEntry(BaseModel):
    finding_id: UUID
    span_start: int
    span_end: int
    redaction_type: str
    policy_version: str


class SanitizeToolResponse(BaseModel):
    trace_id: UUID
    sanitized_document: str
    sanitized_artifact_digest: str
    redaction_map: list[RedactionEntry]


# ── safecontext.classify ──────────────────────────────────────────────────────

class ClassifyToolRequest(BaseModel):
    document: str


class SectionClassification(BaseModel):
    section_id: int
    level: Literal["public", "internal", "confidential", "restricted"]
    justification: str


class ClassifyToolResponse(BaseModel):
    trace_id: UUID
    overall_level: Literal["public", "internal", "confidential", "restricted"]
    sections: list[SectionClassification]


# ── MCP envelope ─────────────────────────────────────────────────────────────

class MCPToolCall(BaseModel):
    tool: str
    version: str = "1.0.0"
    input: dict[str, Any]


class MCPToolCallVersioned(BaseModel):
    """Versioned tool call envelope — clients can pin tool_version (E4.5)."""
    tool: str
    tool_version: str = "1.0.0"   # client can pin version
    input: dict[str, Any]


class MCPToolResult(BaseModel):
    tool: str
    version: str
    output: dict[str, Any]
    trace_id: str | None = None
    error: str | None = None
