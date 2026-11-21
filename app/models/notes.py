"""Text notes and mobile creation idempotency records."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Note(Base):
    """User-owned text note; binary source files stay on the mobile device."""

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_user_project_updated", "user_id", "project_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    refinement_proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    processing_generation: Mapped[int] = mapped_column(default=1, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NoteIdempotencyKey(Base):
    """Idempotency record for safely retrying mobile note creation requests."""

    __tablename__ = "note_idempotency_keys"
    __table_args__ = (Index("uq_note_idempotency_user_key", "user_id", "key", unique=True),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    note_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
