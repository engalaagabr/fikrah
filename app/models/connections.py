"""Stored concept-based relationships between notes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NoteConnection(Base):
    """A note's directed LLM-generated link to a related note."""

    __tablename__ = "note_connections"
    __table_args__ = (
        Index("ix_note_connections_target", "target_note_id"),
        Index("uq_note_connections_pair", "source_note_id", "target_note_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    target_note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
