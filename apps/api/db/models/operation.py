import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base
from db.enums import ActorType, OperationStatus


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('human', 'mcp_agent', 'pipeline')",
            name="ck_operations_actor_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'escalated', 'approved', 'rejected')",
            name="ck_operations_status",
        ),
    )

    # Re-export enums for convenient access: Operation.Status.PENDING, etc.
    Status = OperationStatus
    Actor = ActorType

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # The document text with all PII spans replaced by their redaction markers.
    # Set by sanitizer_agent after applying redactions. None until sanitization runs.
    sanitized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # F6-B2: Cryptographic chain hash — SHA256(prev_chain_hash + operation_hash)
    # NULL for operations created before F6-B2 or when chain is not yet computed.
    chain_hash: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="operations")  # type: ignore[name-defined]  # noqa: F821
    findings: Mapped[list["Finding"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="operation", cascade="all, delete-orphan"
    )
    redactions: Mapped[list["Redaction"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="operation", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="operation", cascade="all, delete-orphan"
    )
