"""PostgreSQL adapter for worker dispatch and vector-cleanup records."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select

from app.infrastructure.sync_database import create_worker_session_factory
from app.models import Note, NoteProcessingJob, VectorCleanupRequest


class WorkerOutboxRepository:
    def __init__(self) -> None:
        self._engine, self._sessions = create_worker_session_factory()

    def close(self) -> None:
        self._engine.dispose()

    def claim_pending(
        self,
        *,
        now: datetime,
        stale_dispatch_after: timedelta,
        stale_processing_after: timedelta,
        batch_size: int,
    ) -> tuple[list[UUID], list[UUID]]:
        job_ids: list[UUID] = []
        cleanup_ids: list[UUID] = []
        with self._sessions.begin() as session:
            jobs = session.scalars(
                select(NoteProcessingJob)
                .where(
                    or_(
                        (NoteProcessingJob.status == "queued")
                        & (
                            NoteProcessingJob.dispatched_at.is_(None)
                            | (
                                NoteProcessingJob.dispatched_at
                                < now - stale_dispatch_after
                            )
                        ),
                        (NoteProcessingJob.status == "processing")
                        & (NoteProcessingJob.started_at < now - stale_processing_after),
                    )
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                if job.status == "processing":
                    note = session.get(Note, job.note_id)
                    if (
                        note is not None
                        and note.revision == job.revision
                        and note.processing_generation == job.processing_generation
                    ):
                        note.processing_status = "queued"
                    job.status = "queued"
                    job.worker_task_id = None
                job.dispatched_at = now
                job.attempt_count += 1
                job_ids.append(job.id)

            cleanup_rows = session.scalars(
                select(VectorCleanupRequest)
                .where(
                    VectorCleanupRequest.completed_at.is_(None),
                    or_(
                        VectorCleanupRequest.dispatched_at.is_(None),
                        VectorCleanupRequest.dispatched_at < now - stale_dispatch_after,
                    ),
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
            for request in cleanup_rows:
                request.dispatched_at = now
                cleanup_ids.append(request.id)
        return job_ids, cleanup_ids

    def pending_vector_cleanup(self, cleanup_id: UUID) -> UUID | None:
        with self._sessions() as session:
            request = session.get(VectorCleanupRequest, cleanup_id)
            if request is None or request.completed_at is not None:
                return None
            return request.note_id

    def complete_vector_cleanup(self, cleanup_id: UUID) -> None:
        with self._sessions.begin() as session:
            request = session.get(
                VectorCleanupRequest, cleanup_id, with_for_update=True
            )
            if request is not None and request.completed_at is None:
                request.completed_at = datetime.now(timezone.utc)
