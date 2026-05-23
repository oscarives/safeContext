from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from core.constants import DOCUMENT_MAX_LENGTH


class ScanRequest(BaseModel):
    document: str = Field(..., max_length=DOCUMENT_MAX_LENGTH)
    document_encoding: Literal["text", "base64"] = "text"
    policy_name: str
    policy_version: str | None = None


class FindingSchema(BaseModel):
    id: UUID
    detector: str
    rule_id: str
    span_start: int
    span_end: int
    confidence: float = Field(ge=0, le=1)
    severity: Literal["low", "medium", "high", "critical"]
    explanation: dict[str, Any]


class ScanResponse(BaseModel):
    trace_id: UUID
    artifact_digest: str  # SHA-256 hex
    policy_version: str
    findings: list[FindingSchema]
    requires_human_review: bool
