"""External-service substitutes and opt-in isolated PostgreSQL test schemas."""

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.models import Note, NoteProcessingJob, Project, User


@pytest.fixture(autouse=True)
def isolated_request_budgets(monkeypatch):
    from app.infrastructure.container import request_budgets

    monkeypatch.setattr(request_budgets._store, "consume", AsyncMock())


@pytest.fixture
def postgres_engine(monkeypatch):
    """Provide an empty disposable schema; never use a non-test database."""
    raw_url = os.getenv("FIKRAH_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "Set FIKRAH_TEST_DATABASE_URL to a dedicated PostgreSQL test database"
        )
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql") or not (url.database or "").endswith(
        "_test"
    ):
        pytest.fail("PostgreSQL regression database must have a name ending in _test")
    schema = f"security_test_{uuid4().hex}"
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped_url)
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    try:
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        control.dispose()


@pytest.fixture
def postgres_case(postgres_engine):
    """Seed the existing worker/auth concurrency scenario in its own schema."""
    Base.metadata.create_all(postgres_engine)
    with Session(postgres_engine) as session:
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
    return postgres_engine, ids
