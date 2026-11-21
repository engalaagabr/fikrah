"""Opt-in PostgreSQL regressions, each using a disposable isolated schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.infrastructure.persistence.worker_notes import WorkerNoteProcessingRepository
from app.infrastructure.persistence.worker_outbox import WorkerOutboxRepository
from app.models import Note, NoteProcessingJob, Project, User


@pytest.fixture
def postgres_case(monkeypatch):
    raw_url = os.getenv("FIKRAH_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set FIKRAH_TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql") or not url.database.endswith("_test"):
        pytest.fail("PostgreSQL regression database must have a name ending in _test")
    schema = f"security_test_{uuid4().hex}"
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped_url)
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            user = User(email="postgres-lock-test@example.com")
            session.add(user)
            session.flush()
            project = Project(user_id=user.id, name="Isolated test")
            session.add(project)
            session.flush()
            note = Note(user_id=user.id, project_id=project.id, content="Lock order")
            session.add(note)
            session.flush()
            job = NoteProcessingJob(note_id=note.id, revision=1)
            session.add(job)
            session.commit()
            ids = (user.id, project.id, note.id, job.id)
        yield engine, ids
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        control.dispose()


def test_note_deletion_does_not_deadlock_with_worker_claim(postgres_case):
    engine, (_, _, note_id, job_id) = postgres_case
    trying_note_lock = Event()

    def observe_note_lock(connection, cursor, statement, parameters, context, many):
        if "FROM notes" in statement and "FOR UPDATE" in statement:
            trying_note_lock.set()

    def claim():
        repository = WorkerNoteProcessingRepository()
        try:
            return repository.claim(
                job_id, "concurrent-worker", datetime.now(timezone.utc) - timedelta(minutes=15)
            )
        finally:
            repository.close()

    event.listen(Engine, "before_cursor_execute", observe_note_lock)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(select(Note.id).where(Note.id == note_id).with_for_update())
                trying_note_lock.clear()
                future = executor.submit(claim)
                assert trying_note_lock.wait(3), "worker never reached the note lock"
                # The blocked worker must not own the job lock yet.
                connection.execute(delete(NoteProcessingJob).where(NoteProcessingJob.id == job_id))
                connection.execute(delete(Note).where(Note.id == note_id))
            assert future.result(timeout=5) is None
    finally:
        event.remove(Engine, "before_cursor_execute", observe_note_lock)


def test_dispatcher_skips_notes_locked_by_another_transaction(postgres_case):
    engine, (_, _, note_id, _) = postgres_case
    repository = WorkerOutboxRepository()
    try:
        with engine.begin() as connection:
            connection.execute(select(Note.id).where(Note.id == note_id).with_for_update())
            assert repository.claim_pending(
                now=datetime.now(timezone.utc),
                stale_dispatch_after=timedelta(minutes=5),
                stale_processing_after=timedelta(minutes=15),
                batch_size=10,
            ) == ([], [])
    finally:
        repository.close()
