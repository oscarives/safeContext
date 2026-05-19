import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        # Partial index for efficient polling of unprocessed events (SKILL-DATA)
        Index("idx_outbox_processed", "processed", postgresql_where="processed = false"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
