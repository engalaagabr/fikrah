"""Celery tasks for note processing and Qdrant cleanup."""

from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

from celery import Task
from qdrant_client import QdrantClient, models as qdrant_models
from sqlalchemy import create_engine, delete, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.ai.providers import AIProviderFactory
from app.models import Note, NoteConnection, NoteProcessingJob, VectorCleanupRequest
from app.worker.celery_app import celery_app

_STALE_DISPATCH_AFTER = timedelta(minutes=5)
_STALE_PROCESSING_AFTER = timedelta(minutes=15)
_MAX_CONNECTIONS_PER_NOTE = 10


def _session_factory() -> tuple[object, sessionmaker[Session]]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required by the Celery worker")
    url = make_url(database_url)
    if url.drivername in {"postgresql", "postgresql+asyncpg"}:
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _qdrant_client() -> tuple[QdrantClient, str, int]:
    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        raise RuntimeError("QDRANT_URL is required by the Celery worker")
    dimensions = int(os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768"))
    client = QdrantClient(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY"), timeout=30)
    collection_name = os.getenv("QDRANT_NOTES_COLLECTION", "fikrah-notes")
    collections = {item.name for item in client.get_collections().collections}
    if collection_name not in collections:
        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=dimensions, distance=qdrant_models.Distance.COSINE
                ),
            )
        except Exception:
            # Another worker may have created the collection concurrently.
            collections = {item.name for item in client.get_collections().collections}
            if collection_name not in collections:
                raise
    return client, collection_name, dimensions


def _normalized_concepts(concepts: list[str]) -> set[str]:
    return {concept.strip().casefold() for concept in concepts if concept.strip()}


def _refresh_note_connections(session: Session, note: Note) -> None:
    """Replace this note's outgoing concept links with its strongest matches."""
    own_concepts = _normalized_concepts(note.concepts)
    session.execute(
        delete(NoteConnection).where(NoteConnection.source_note_id == note.id)
    )
    if not own_concepts:
        return

    candidates = session.scalars(
        select(Note)
        .where(
            Note.id != note.id,
            Note.user_id == note.user_id,
            Note.project_id == note.project_id,
            Note.processing_status == "completed",
        )
        .order_by(Note.updated_at.desc(), Note.id)
    ).all()
    related: list[tuple[int, Note]] = []
    for candidate in candidates:
        overlap = own_concepts & _normalized_concepts(candidate.concepts)
        if overlap:
            related.append((len(overlap), candidate))

    # Candidates already arrive newest-first; the stable sort uses recency for ties.
    related.sort(key=lambda item: -item[0])
    table = NoteConnection.__table__
    dialect = session.get_bind().dialect.name
    for _, candidate in related[:_MAX_CONNECTIONS_PER_NOTE]:
        values = {"source_note_id": note.id, "target_note_id": candidate.id}
        if dialect == "postgresql":
            statement = pg_insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["source_note_id", "target_note_id"]
            )
            session.execute(statement)
        elif dialect == "sqlite":
            statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["source_note_id", "target_note_id"]
            )
            session.execute(statement)
        else:
            session.add(NoteConnection(**values))


class NoteProcessingTask(Task):
    """Persist terminal failure after Celery exhausts configured retries."""

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:  # noqa: ANN001
        if not args:
            return
        try:
            engine, sessions = _session_factory()
            with sessions() as session:
                job = session.get(NoteProcessingJob, UUID(args[0]))
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
                session.commit()
        finally:
            if "engine" in locals():
                engine.dispose()


@celery_app.task(
    bind=True,
    base=NoteProcessingTask,
    name="app.worker.tasks.process_note_job",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_note_job(self, job_id: str) -> None:  # noqa: ANN001
    engine, sessions = _session_factory()
    try:
        with sessions.begin() as session:
            job = session.scalar(
                select(NoteProcessingJob)
                .where(NoteProcessingJob.id == UUID(job_id))
                .with_for_update()
            )
            if job is None or job.status in {"completed", "stale", "failed"}:
                return
            now = datetime.now(timezone.utc)
            if (
                job.status == "processing"
                and job.worker_task_id != self.request.id
                and job.started_at is not None
                and job.started_at > now - _STALE_PROCESSING_AFTER
            ):
                return
            note = session.scalar(
                select(Note).where(Note.id == job.note_id).with_for_update()
            )
            if (
                note is None
                or note.revision != job.revision
                or note.processing_generation != job.processing_generation
            ):
                job.status = "stale"
                return
            job.status = "processing"
            job.worker_task_id = self.request.id
            job.started_at = now
            job.attempt_count += 1
            note.processing_status = "processing"
            note_snapshot = (
                note.id,
                note.user_id,
                note.project_id,
                note.revision,
                note.processing_generation,
                note.content,
            )

        note_id, user_id, project_id, revision, processing_generation, content = note_snapshot
        analysis = AIProviderFactory.create_text_model().analyze_note(content)
        embedding = AIProviderFactory.create_embedding_model().embed_note(content)
        client, collection, dimensions = _qdrant_client()
        try:
            if len(embedding) != dimensions:
                raise ValueError(f"Expected {dimensions}-dimensional embedding, received {len(embedding)}")
            with sessions.begin() as session:
                # Serialize relation refreshes per project so two notes finishing
                # concurrently cannot both miss each other as still-processing.
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtextextended(:project_id, 0))"),
                        {"project_id": str(project_id)},
                    )
                job = session.scalar(
                    select(NoteProcessingJob)
                    .where(NoteProcessingJob.id == UUID(job_id))
                    .with_for_update()
                )
                note = session.scalar(select(Note).where(Note.id == note_id).with_for_update())
                if job is None:
                    return
                if (
                    note is None
                    or note.revision != revision
                    or note.processing_generation != processing_generation
                ):
                    job.status = "stale"
                    return
                # Keep the note row lock while upserting so a concurrent edit/delete
                # cannot make an old vector the last write for this note ID.
                client.upsert(
                    collection_name=collection,
                    points=[qdrant_models.PointStruct(
                        id=str(note_id),
                        vector=embedding,
                        payload={
                            "user_id": str(user_id),
                            "project_id": str(project_id),
                            "revision": revision,
                            "processing_generation": processing_generation,
                        },
                    )],
                    wait=True,
                )
                if note.title is None:
                    note.title = analysis.title
                note.refinement_proposal = analysis.refinement_proposal
                note.concepts = analysis.concepts[:8]
                note.processing_status = "completed"
                _refresh_note_connections(session, note)
                job.status = "completed"
        finally:
            client.close()
    finally:
        engine.dispose()


@celery_app.task(name="app.worker.tasks.delete_note_vector", acks_late=True)
def delete_note_vector(cleanup_id: str) -> None:
    engine, sessions = _session_factory()
    client: QdrantClient | None = None
    try:
        with sessions() as session:
            request = session.get(VectorCleanupRequest, UUID(cleanup_id))
            if request is None or request.completed_at is not None:
                return
            note_id = request.note_id

        client, collection, _ = _qdrant_client()
        collections = {item.name for item in client.get_collections().collections}
        if collection in collections:
            client.delete(
                collection_name=collection,
                points_selector=qdrant_models.PointIdsList(points=[str(note_id)]),
                wait=True,
            )
        with sessions.begin() as session:
            request = session.get(VectorCleanupRequest, UUID(cleanup_id), with_for_update=True)
            if request is not None and request.completed_at is None:
                request.completed_at = datetime.now(timezone.utc)
    finally:
        if client is not None:
            client.close()
        engine.dispose()


@celery_app.task(name="app.worker.tasks.dispatch_pending_work")
def dispatch_pending_work() -> None:
    """Publish durable PostgreSQL outbox records, recovering stale dispatches."""
    engine, sessions = _session_factory()
    now = datetime.now(timezone.utc)
    job_ids: list[UUID] = []
    cleanup_ids: list[UUID] = []
    try:
        with sessions.begin() as session:
            jobs = session.scalars(
                select(NoteProcessingJob)
                .where(
                    or_(
                        (NoteProcessingJob.status == "queued")
                        & (
                            NoteProcessingJob.dispatched_at.is_(None)
                            | (NoteProcessingJob.dispatched_at < now - _STALE_DISPATCH_AFTER)
                        ),
                        (NoteProcessingJob.status == "processing")
                        & (NoteProcessingJob.started_at < now - _STALE_PROCESSING_AFTER),
                    )
                )
                .limit(100)
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
                        VectorCleanupRequest.dispatched_at < now - _STALE_DISPATCH_AFTER,
                    ),
                )
                .limit(100)
                .with_for_update(skip_locked=True)
            ).all()
            for request in cleanup_rows:
                request.dispatched_at = now
                cleanup_ids.append(request.id)

        for job_id in job_ids:
            process_note_job.apply_async(args=[str(job_id)])
        for cleanup_id in cleanup_ids:
            delete_note_vector.apply_async(args=[str(cleanup_id)])
    finally:
        engine.dispose()
