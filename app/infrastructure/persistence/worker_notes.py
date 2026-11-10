"""Synchronous note-processing persistence adapter for Celery workers."""

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text

from app.connections.persistence import refresh_note_connections
from app.infrastructure.sync_database import create_worker_session_factory
from app.llm.contracts import NoteAnalysis
from app.models import Note, NoteProcessingJob
from app.notes.processing import NoteProcessingSnapshot


class WorkerNoteProcessingRepository:
    def __init__(self) -> None:
        self._engine, self._sessions = create_worker_session_factory()

    def close(self) -> None:
        self._engine.dispose()

    def claim(
        self, job_id: UUID, worker_task_id: str, stale_before: datetime
    ) -> NoteProcessingSnapshot | None:
        with self._sessions.begin() as session:
            job = session.scalar(
                select(NoteProcessingJob)
                .where(NoteProcessingJob.id == job_id)
                .with_for_update()
            )
            if job is None or job.status in {"completed", "stale", "failed"}:
                return None
            if (
                job.status == "processing"
                and job.worker_task_id != worker_task_id
                and job.started_at is not None
                and job.started_at > stale_before
            ):
                return None
            note = session.scalar(
                select(Note).where(Note.id == job.note_id).with_for_update()
            )
            if (
                note is None
                or note.revision != job.revision
                or note.processing_generation != job.processing_generation
            ):
                job.status = "stale"
                return None

            now = datetime.now(timezone.utc)
            job.status = "processing"
            job.worker_task_id = worker_task_id
            job.started_at = now
            job.attempt_count += 1
            note.processing_status = "processing"
            return NoteProcessingSnapshot(
                job_id=job.id,
                note_id=note.id,
                user_id=note.user_id,
                project_id=note.project_id,
                revision=note.revision,
                processing_generation=note.processing_generation,
                content=note.content,
            )

    def complete_if_current(
        self,
        snapshot: NoteProcessingSnapshot,
        analysis: NoteAnalysis,
        persist_vector: Callable[[], None],
    ) -> bool:
        with self._sessions.begin() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:project_id, 0))"
                    ),
                    {"project_id": str(snapshot.project_id)},
                )
            job = session.scalar(
                select(NoteProcessingJob)
                .where(NoteProcessingJob.id == snapshot.job_id)
                .with_for_update()
            )
            note = session.scalar(
                select(Note).where(Note.id == snapshot.note_id).with_for_update()
            )
            if job is None:
                return False
            if (
                note is None
                or note.revision != snapshot.revision
                or note.processing_generation != snapshot.processing_generation
            ):
                job.status = "stale"
                return False

            # Hold the note lock across the vector write to prevent an older
            # processing result from overwriting a newer revision's vector.
            persist_vector()
            if note.title is None:
                note.title = analysis.title
            note.refinement_proposal = analysis.refinement_proposal
            note.concepts = analysis.concepts[:8]
            note.processing_status = "completed"
            refresh_note_connections(session, note)
            job.status = "completed"
            return True

    def mark_failed(self, job_id: UUID) -> None:
        with self._sessions.begin() as session:
            job = session.get(NoteProcessingJob, job_id)
            if job is None:
                return
            note = session.get(Note, job.note_id)
            job.status = "failed"
            if (
                note is not None
                and note.revision == job.revision
                and note.processing_generation == job.processing_generation
            ):
                note.processing_status = "failed"
