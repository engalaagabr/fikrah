"""Durable note processing and vector cleanup records."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NoteProcessingJob(Base):
    """Durable processing intent committed with the note revision."""

    __tablename__ = "note_processing_jobs"
    __table_args__ = (Index("ix_note_processing_jobs_status_created", "status", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    processing_generation: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VectorCleanupRequest(Base):
    """Durable Qdrant cleanup intent; deliberately survives note deletion."""

    __tablename__ = "vector_cleanup_requests"
    __table_args__ = (Index("ix_vector_cleanup_requests_created", "completed_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    note_id: Mapped[UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
