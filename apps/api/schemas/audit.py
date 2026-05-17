from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class FindingAuditSchema(BaseModel):
    id: UUID
    detector: str
    rule_id: str
    span_start: int
    span_end: int
    confidence: float
    severity: str
    explanation: dict[str, Any]


class RedactionAuditSchema(BaseModel):
    id: UUID
    finding_id: UUID
    redaction_type: str
    policy_version: str
    applied_at: datetime
    approved_by: UUID | None
    approval_trace_id: UUID | None


class ArtifactAuditSchema(BaseModel):
    id: UUID
    artifact_type: str
    minio_key: str
    digest: str
    worm_locked: bool
    created_at: datetime


class AuditExportResponse(BaseModel):
    trace_id: UUID
    exported_at: datetime
    operation: dict[str, Any]   # all fields from Operation
    findings: list[FindingAuditSchema]
    redactions: list[RedactionAuditSchema]
    artifacts: list[ArtifactAuditSchema]
    hmac_signature: str          # HMAC-SHA256 of serialized payload
