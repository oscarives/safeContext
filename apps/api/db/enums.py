"""Centralized enums for Operation status, actor_type, and related constants.

These Python enums are the single source of truth for the valid values.
The DB CHECK constraints in migrations enforce the same values at the
database level. When adding a new enum member, update both the enum here
and the corresponding migration/constraint.
"""

from enum import StrEnum


class OperationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActorType(StrEnum):
    HUMAN = "human"
    MCP_AGENT = "mcp_agent"
    PIPELINE = "pipeline"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RedactionType(StrEnum):
    MASK = "mask"
    REMOVE = "remove"
    REPLACE = "replace"


class ArtifactType(StrEnum):
    ORIGINAL = "original"
    SANITIZED = "sanitized"
    AUDIT_EXPORT = "audit_export"


class WaiverStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
