import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_findings_confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSONB, nullable=False)

    operation: Mapped["Operation"] = relationship(back_populates="findings")  # type: ignore[name-defined]  # noqa: F821
    redactions: Mapped[list["Redaction"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="finding", cascade="all, delete-orphan"
    )
