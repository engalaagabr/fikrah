"""Celery tasks for note processing and Qdrant cleanup."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.infrastructure.persistence.worker_outbox import WorkerOutboxRepository
from app.infrastructure.worker_container import create_note_processing_service
from app.rag.vector_store import QdrantNoteVectorStore
from app.workers.celery_app import celery_app, settings

_STALE_DISPATCH_AFTER = timedelta(seconds=settings.stale_dispatch_after_seconds)
_STALE_PROCESSING_AFTER = timedelta(seconds=settings.stale_processing_after_seconds)


@celery_app.task(
    bind=True,
    name="app.worker.tasks.process_note_job",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=settings.retry_backoff_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.max_retries},
)
def process_note_job(self, job_id: str) -> None:
    service, repository = create_note_processing_service(_STALE_PROCESSING_AFTER)
    try:
        service.process(
            UUID(job_id), self.request.id,
            terminal_on_error=self.request.retries >= settings.max_retries,
        )
    finally:
        repository.close()


@celery_app.task(name="app.worker.tasks.delete_note_vector", acks_late=True)
def delete_note_vector(cleanup_id: str) -> None:
    repository = WorkerOutboxRepository()
    try:
        note_id = repository.pending_vector_cleanup(UUID(cleanup_id))
        if note_id is None:
            return
        QdrantNoteVectorStore().delete_note(note_id)
        repository.complete_vector_cleanup(UUID(cleanup_id))
    finally:
        repository.close()


@celery_app.task(name="app.worker.tasks.dispatch_pending_work")
def dispatch_pending_work() -> None:
    """Publish durable PostgreSQL outbox records, recovering stale dispatches."""
    repository = WorkerOutboxRepository()
    try:
        job_ids, cleanup_ids = repository.claim_pending(
            now=datetime.now(timezone.utc),
            stale_dispatch_after=_STALE_DISPATCH_AFTER,
            stale_processing_after=_STALE_PROCESSING_AFTER,
            batch_size=settings.dispatch_batch_size,
        )
        for job_id in job_ids:
            process_note_job.apply_async(args=[str(job_id)])
        for cleanup_id in cleanup_ids:
            delete_note_vector.apply_async(args=[str(cleanup_id)])
    finally:
        repository.close()
