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
        pytest.skip(
            "Set FIKRAH_TEST_DATABASE_URL to a dedicated PostgreSQL test database"
        )
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql") or not url.database.endswith(
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
                job_id,
                "concurrent-worker",
                datetime.now(timezone.utc) - timedelta(minutes=15),
            )
        finally:
            repository.close()

    event.listen(Engine, "before_cursor_execute", observe_note_lock)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(
                    select(Note.id).where(Note.id == note_id).with_for_update()
                )
                trying_note_lock.clear()
                future = executor.submit(claim)
                assert trying_note_lock.wait(3), "worker never reached the note lock"
                # The blocked worker must not own the job lock yet.
                connection.execute(
                    delete(NoteProcessingJob).where(NoteProcessingJob.id == job_id)
                )
                connection.execute(delete(Note).where(Note.id == note_id))
            assert future.result(timeout=5) is None
    finally:
        event.remove(Engine, "before_cursor_execute", observe_note_lock)


def test_dispatcher_skips_notes_locked_by_another_transaction(postgres_case):
    engine, (_, _, note_id, _) = postgres_case
    repository = WorkerOutboxRepository()
    try:
        with engine.begin() as connection:
            connection.execute(
                select(Note.id).where(Note.id == note_id).with_for_update()
            )
            assert repository.claim_pending(
                now=datetime.now(timezone.utc),
                stale_dispatch_after=timedelta(minutes=5),
                stale_processing_after=timedelta(minutes=15),
                batch_size=10,
            ) == ([], [])
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_first_google_requests_create_one_account(postgres_case, monkeypatch):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.contracts.auth import GoogleIdentityToken
    from app.services.auth_service import AuthService

    engine, _ = postgres_case
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    url = engine.url.set(drivername="postgresql+asyncpg", query={})
    async_engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "postgres-auth-test-private-secret-32-characters"
    )

    async def discard(*_):
        pass

    service = AuthService(
        protect_email_token=lambda token: token,
        reveal_email_token=lambda token: token,
        send_action_email=discard,
        send_welcome_email=discard,
        google_client_id=lambda: "test-client",
        verify_google_id_token=lambda *_: {
            "sub": "simultaneous-google-subject",
            "email": "simultaneous@gmail.com",
            "email_verified": True,
        },
    )
    barrier = asyncio.Barrier(2)

    async def login():
        async with sessions() as db:
            await barrier.wait()
            return await service.google_login(
                GoogleIdentityToken(id_token="test-token"), db
            )

    try:
        pairs = await asyncio.gather(login(), login())
        assert all(pair.access_token for pair in pairs)
        with Session(engine) as db:
            assert (
                db.scalar(
                    select(func.count(User.id)).where(
                        User.email == "simultaneous@gmail.com"
                    )
                )
                == 1
            )
    finally:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_password_reset_serializes_with_refresh(postgres_case, monkeypatch):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.contracts.auth import PasswordReset, RefreshToken
    from app.core.security import hash_opaque_token
    from app.models import EmailActionToken, RefreshSession
    from app.repositories.auth import AuthRepository
    from app.services.auth_errors import AuthServiceError
    from app.services.auth_service import AuthService, _issue_session

    engine, (user_id, _, _, _) = postgres_case
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    url = engine.url.set(drivername="postgresql+asyncpg", query={})
    async_engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "postgres-auth-test-private-secret-32-characters"
    )
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.get(User, user_id).email_verified_at = now
        db.add(
            EmailActionToken(
                user_id=user_id,
                token_hash=hash_opaque_token("reset-test-token"),
                purpose="reset_password",
                expires_at=now + timedelta(hours=1),
            )
        )
        db.commit()
    async with sessions() as db:
        tokens = await _issue_session(db, await db.get(User, user_id), AuthRepository())
        await db.commit()

    async def discard(*_):
        pass

    service = AuthService(
        protect_email_token=lambda token: token,
        reveal_email_token=lambda token: token,
        send_action_email=discard,
        send_welcome_email=discard,
        google_client_id=lambda: None,
        verify_google_id_token=lambda *_: {},
    )
    both_waiting = asyncio.Event()
    lock_requests = 0

    def observe(connection, cursor, statement, parameters, context, many):
        nonlocal lock_requests
        if "FROM users" in statement and "FOR UPDATE" in statement:
            lock_requests += 1
            if lock_requests == 2:
                both_waiting.set()

    async def reset():
        async with sessions() as db:
            return await service.confirm_password_reset(
                PasswordReset(
                    token="reset-test-token",
                    new_password="a new safe PostgreSQL test passphrase",
                ),
                db,
            )

    async def refresh():
        async with sessions() as db:
            try:
                return await service.refresh(
                    RefreshToken(refresh_token=tokens.refresh_token), db
                )
            except AuthServiceError as error:
                assert error.status_code == 401
                return None

    event.listen(async_engine.sync_engine, "before_cursor_execute", observe)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(
                select(User.id).where(User.id == user_id).with_for_update()
            )
            pending = [asyncio.create_task(reset()), asyncio.create_task(refresh())]
            try:
                await asyncio.wait_for(both_waiting.wait(), timeout=5)
            finally:
                transaction.commit()
            await asyncio.wait_for(asyncio.gather(*pending), timeout=10)
        with Session(engine) as db:
            assert (
                db.scalar(
                    select(func.count(RefreshSession.id)).where(
                        RefreshSession.user_id == user_id,
                        RefreshSession.revoked_at.is_(None),
                    )
                )
                == 0
            )
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", observe)
        await async_engine.dispose()


def test_session_family_migration_retires_legacy_tokens(postgres_case):
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine, (user_id, _, _, _) = postgres_case
    revision = import_module(
        "migrations.versions.20261121_01_add_refresh_session_families"
    )
    legacy_id = uuid4()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE refresh_sessions DROP COLUMN family_id"))
        connection.execute(
            text(
                "INSERT INTO refresh_sessions (id, user_id, token_hash, expires_at) VALUES (:id, :user_id, :token_hash, :expires_at)"
            ),
            {
                "id": legacy_id,
                "user_id": user_id,
                "token_hash": "legacy-token-hash",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            },
        )
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        row = connection.execute(
            text("SELECT family_id, revoked_at FROM refresh_sessions WHERE id=:id"),
            {"id": legacy_id},
        ).one()
        assert row.family_id == legacy_id
        assert row.revoked_at is not None


@pytest.mark.asyncio
async def test_concurrent_email_delivery_claim_sends_once(postgres_case):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import EmailDelivery
    from app.services.email_delivery_service import EmailDeliveryService

    engine, (user_id, _, _, _) = postgres_case
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    url = engine.url.set(drivername="postgresql+asyncpg", query={})
    async_engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    with Session(engine) as db:
        delivery = EmailDelivery(
            user_id=user_id, recipient="delivery@example.com", purpose="welcome"
        )
        db.add(delivery)
        db.commit()
        delivery_id = delivery.id
    sending = asyncio.Event()
    release = asyncio.Event()
    sent = []

    async def send(email):
        sent.append(email)
        sending.set()
        await release.wait()

    sender = EmailDeliveryService(send, send, lambda token: token)

    async def deliver():
        async with sessions() as db:
            return await sender.deliver(db, delivery_id)

    try:
        first = asyncio.create_task(deliver())
        await asyncio.wait_for(sending.wait(), timeout=5)
        try:
            assert not await asyncio.wait_for(deliver(), timeout=3)
        finally:
            release.set()
        assert await asyncio.wait_for(first, timeout=3)
        assert sent == ["delivery@example.com"]
    finally:
        await async_engine.dispose()


def test_email_outbox_migration_creates_encrypted_delivery_table(postgres_case):
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine, _ = postgres_case
    revision = import_module("migrations.versions.20261121_02_add_account_email_outbox")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE email_deliveries"))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        assert connection.scalar(text("SELECT count(*) FROM email_deliveries")) == 0
