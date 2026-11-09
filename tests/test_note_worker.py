from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.providers import NoteAnalysis
from app.models import Note, NoteProcessingJob, Project, User, VectorCleanupRequest
from app.models.base import Base
from app.worker.tasks import process_note_job


class FakeTextModel:
    def analyze_note(self, content: str) -> NoteAnalysis:
        assert content == "Original thought"
        return NoteAnalysis(
            title="Generated title",
            refinement_proposal="A clearer version of the thought.",
            concepts=["knowledge", "ideas"],
        )


class FakeEmbeddingModel:
    def embed_note(self, content: str) -> list[float]:
        assert content == "Original thought"
        return [0.1, 0.2, 0.3]


class FakeQdrant:
    def __init__(self) -> None:
        self.points = []
        self.closed = False

    def upsert(self, **kwargs: object) -> None:
        self.points.extend(kwargs["points"])

    def close(self) -> None:
        self.closed = True

    def get_collections(self) -> SimpleNamespace:
        return SimpleNamespace(collections=[SimpleNamespace(name="notes")])

    def delete(self, **kwargs: object) -> None:
        self.deleted = kwargs


@pytest.fixture
def note_job_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_path = tmp_path / "worker.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        user = User(email="worker@example.com", email_verified_at=now)
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, name="General", is_general=True)
        session.add(project)
        session.flush()
        note = Note(
            user_id=user.id,
            project_id=project.id,
            content="Original thought",
            title=None,
            revision=1,
            processing_status="queued",
        )
        session.add(note)
        session.flush()
        job = NoteProcessingJob(note_id=note.id, revision=1, status="queued")
        session.add(job)
        session.commit()
        job_id, note_id = job.id, note.id
    yield database_path, job_id, note_id
    engine.dispose()


def test_celery_job_analyzes_current_revision_and_upserts_embedding(
    note_job_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker import tasks

    database_path, job_id, note_id = note_job_db
    qdrant = FakeQdrant()
    monkeypatch.setattr(tasks.AIProviderFactory, "create_text_model", lambda: FakeTextModel())
    monkeypatch.setattr(tasks.AIProviderFactory, "create_embedding_model", lambda: FakeEmbeddingModel())
    monkeypatch.setattr(tasks, "_qdrant_client", lambda: (qdrant, "notes", 3))

    result = process_note_job.apply(args=[str(job_id)], task_id="worker-task-1", throw=True)
    assert result.successful()
    assert qdrant.closed
    assert len(qdrant.points) == 1
    assert qdrant.points[0].id == str(note_id)
    assert qdrant.points[0].payload["revision"] == 1

    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        note = session.get(Note, note_id)
        job = session.get(NoteProcessingJob, job_id)
        assert note is not None and job is not None
        assert note.title == "Generated title"
        assert note.content == "Original thought"
        assert note.refinement_proposal == "A clearer version of the thought."
        assert note.concepts == ["knowledge", "ideas"]
        assert note.processing_status == "completed"
        assert job.status == "completed"
    engine.dispose()


def test_stale_note_job_does_not_call_ai_or_overwrite_new_revision(
    note_job_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker import tasks

    database_path, job_id, note_id = note_job_db
    update_engine = create_engine(f"sqlite:///{database_path}")
    with Session(update_engine) as session:
        note = session.get(Note, note_id)
        assert note is not None
        note.revision = 2
        note.content = "New version"
        session.commit()
    update_engine.dispose()

    class FailIfCalled:
        def analyze_note(self, content: str) -> NoteAnalysis:
            raise AssertionError("stale note revision must not call AI")

    monkeypatch.setattr(tasks.AIProviderFactory, "create_text_model", lambda: FailIfCalled())
    result = process_note_job.apply(args=[str(job_id)], task_id="worker-task-2", throw=True)
    assert result.successful()

    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        note = session.get(Note, note_id)
        job = session.get(NoteProcessingJob, job_id)
        assert note is not None and job is not None
        assert note.revision == 2
        assert note.content == "New version"
        assert note.processing_status == "queued"
        assert job.status == "stale"
    engine.dispose()


def test_stale_processing_generation_does_not_overwrite_new_refinement_request(
    note_job_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker import tasks

    database_path, job_id, note_id = note_job_db
    update_engine = create_engine(f"sqlite:///{database_path}")
    with Session(update_engine) as session:
        note = session.get(Note, note_id)
        assert note is not None
        note.processing_generation = 2
        session.commit()
    update_engine.dispose()

    class FailIfCalled:
        def analyze_note(self, content: str) -> NoteAnalysis:
            raise AssertionError("stale processing generation must not call AI")

    monkeypatch.setattr(tasks.AIProviderFactory, "create_text_model", lambda: FailIfCalled())
    result = process_note_job.apply(args=[str(job_id)], task_id="worker-task-old-generation", throw=True)
    assert result.successful()

    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        note = session.get(Note, note_id)
        job = session.get(NoteProcessingJob, job_id)
        assert note is not None and job is not None
        assert note.revision == 1
        assert note.processing_generation == 2
        assert note.processing_status == "queued"
        assert job.status == "stale"
    engine.dispose()


def test_dispatcher_publishes_durable_pending_note_job(note_job_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.worker import tasks

    database_path, job_id, _ = note_job_db
    published: list[str] = []
    monkeypatch.setattr(
        tasks.process_note_job,
        "apply_async",
        lambda args: published.append(args[0]),
    )

    tasks.dispatch_pending_work.run()

    assert published == [str(job_id)]
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        job = session.get(NoteProcessingJob, job_id)
        assert job is not None
        assert job.dispatched_at is not None
        assert job.attempt_count == 1
    engine.dispose()


def test_vector_cleanup_worker_removes_qdrant_point_and_marks_request_complete(
    note_job_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker import tasks
    from app.worker.tasks import delete_note_vector

    database_path, _, note_id = note_job_db
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        request = VectorCleanupRequest(note_id=note_id)
        session.add(request)
        session.commit()
        cleanup_id = request.id
    engine.dispose()

    qdrant = FakeQdrant()
    monkeypatch.setattr(tasks, "_qdrant_client", lambda: (qdrant, "notes", 3))
    result = delete_note_vector.apply(args=[str(cleanup_id)], task_id="cleanup-task", throw=True)

    assert result.successful()
    assert qdrant.deleted["collection_name"] == "notes"
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        request = session.get(VectorCleanupRequest, cleanup_id)
        assert request is not None and request.completed_at is not None
    engine.dispose()
