from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class FindingAuditSchema(BaseModel):
    id: UUID
    detector: str
    rule_id: str
    span_start: int
    span_end: int
    confidence: float
    severity: Literal["low", "medium", "high", "critical"]
    explanation: dict[str, Any]


class RedactionAuditSchema(BaseModel):
    id: UUID
    finding_id: UUID
    redaction_type: Literal["mask", "remove", "replace"]
    policy_version: str
    applied_at: datetime
    approved_by: UUID | None
    approval_trace_id: UUID | None


class ArtifactAuditSchema(BaseModel):
    id: UUID
    artifact_type: Literal["original", "sanitized", "audit_export"]
    minio_key: str
    digest: str
    worm_locked: bool
    created_at: datetime


class AuditExportResponse(BaseModel):
    trace_id: UUID
    exported_at: datetime
    operation: dict[str, Any]  # all fields from Operation
    findings: list[FindingAuditSchema]
    redactions: list[RedactionAuditSchema]
    artifacts: list[ArtifactAuditSchema]
    hmac_signature: str  # HMAC-SHA256 of serialized payload
    # The document with all PII/secret spans replaced by [REDACTED].
    # None if the operation is still pending sanitization.
    # Use this field to safely pass the document to an LLM or downstream system.
    sanitized_document: str | None = None
    # F6-B1: RFC 3161 TSA token (base64-encoded DER) — non-repudiation proof
    tsa_token: str | None = None
    # F6-B2: Chain hash for tamper detection
    chain_hash: str | None = None
    # F6-B3: Digital signature from OpenBao Transit engine (base64).
    # F7-5: when present this is the WRITE-TIME signature persisted at completion
    # (operation.event_signature) — bound to the event as it occurred. Falls back
    # to a read-time signature only for legacy operations sealed before F7-5.
    digital_signature: str | None = None
    # F7-5: True when digital_signature was produced at write-time (authoritative
    # non-repudiation evidence); False when it is a read-time fallback.
    signature_at_write_time: bool = False
    # F7-5: ISO timestamp when the write-time signature was produced.
    event_signed_at: datetime | None = None
    # F7-5: Transit key version that produced the write-time signature
    # (needed to verify after key rotation — see F7-2).
    signing_key_version: int | None = None
