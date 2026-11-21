"""PostgreSQL ownership integrity from ORM metadata and real Alembic history."""

from io import StringIO
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, insert, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.base import Base
from app.models import (
    ChatConversation,
    ChatMessage,
    ChatMessageSource,
    Note,
    NoteConnection,
    NoteProcessingJob,
    Project,
    User,
    VectorCleanupRequest,
)

PREVIOUS_REVISION = "20261121_02"


def seed_owners(engine):
    ids = {
        name: uuid4()
        for name in (
            "owner",
            "stranger",
            "project",
            "other_project",
            "same_owner_project",
            "note",
            "other_note",
            "conversation",
            "other_conversation",
        )
    }
    with engine.begin() as db:
        db.execute(
            insert(User),
            [
                {"id": ids["owner"], "email": "owner@example.com"},
                {"id": ids["stranger"], "email": "stranger@example.com"},
            ],
        )
        db.execute(
            insert(Project),
            [
                {
                    "id": ids["project"],
                    "user_id": ids["owner"],
                    "name": "Owner project",
                },
                {
                    "id": ids["same_owner_project"],
                    "user_id": ids["owner"],
                    "name": "Second project",
                },
                {
                    "id": ids["other_project"],
                    "user_id": ids["stranger"],
                    "name": "Stranger project",
                },
            ],
        )
        db.execute(
            insert(Note),
            [
                {
                    "id": ids["note"],
                    "user_id": ids["owner"],
                    "project_id": ids["project"],
                    "content": "Owner content",
                },
                {
                    "id": ids["other_note"],
                    "user_id": ids["stranger"],
                    "project_id": ids["other_project"],
                    "content": "Stranger content",
                },
            ],
        )
        db.execute(
            insert(ChatConversation),
            [
                {
                    "id": ids["conversation"],
                    "user_id": ids["owner"],
                    "project_id": ids["project"],
                    "title": "Owner chat",
                },
                {
                    "id": ids["other_conversation"],
                    "user_id": ids["stranger"],
                    "project_id": ids["other_project"],
                    "title": "Stranger chat",
                },
            ],
        )
    return ids


def assert_ownership_constraints(engine):
    schema = inspect(engine)
    assert {"id", "user_id"} == set(
        next(
            item["column_names"]
            for item in schema.get_unique_constraints("projects")
            if item["name"] == "uq_projects_id_user_id"
        )
    )
    for table in ("notes", "chat_conversations"):
        foreign_keys = [
            fk
            for fk in schema.get_foreign_keys(table)
            if fk["referred_table"] == "projects"
        ]
        assert len(foreign_keys) == 1
        constraint = foreign_keys[0]
        assert constraint["name"] == f"fk_{table}_project_owner"
        assert constraint["constrained_columns"] == ["project_id", "user_id"]
        assert constraint["referred_columns"] == ["id", "user_id"]
        assert constraint["options"]["ondelete"] == "CASCADE"


@pytest.fixture(params=["metadata", "migrations"])
def ownership_case(postgres_engine, request):
    if request.param == "metadata":
        Base.metadata.create_all(postgres_engine)
    else:
        command.upgrade(Config("alembic.ini"), "head")
    assert_ownership_constraints(postgres_engine)
    return postgres_engine, seed_owners(postgres_engine)


@pytest.mark.parametrize(
    ("model", "key"), [(Note, "note"), (ChatConversation, "conversation")]
)
@pytest.mark.parametrize("operation", ["insert", "update_user", "update_project"])
def test_database_rejects_mismatched_project_ownership(
    ownership_case, model, key, operation
):
    engine, ids = ownership_case
    with pytest.raises(IntegrityError) as caught, engine.begin() as db:
        if operation == "insert":
            values = {"user_id": ids["stranger"], "project_id": ids["project"]}
            if model is Note:
                values["content"] = "Rejected content"
            db.execute(insert(model).values(**values))
        else:
            values = (
                {"user_id": ids["stranger"]}
                if operation == "update_user"
                else {"project_id": ids["other_project"]}
            )
            db.execute(update(model).where(model.id == ids[key]).values(**values))
    assert caught.value.orig.sqlstate == "23503"
    assert (
        caught.value.orig.diag.constraint_name
        == f"fk_{model.__tablename__}_project_owner"
    )
    with engine.connect() as db:
        row = db.execute(
            select(model.user_id, model.project_id).where(model.id == ids[key])
        ).one()
        assert tuple(row) == (ids["owner"], ids["project"])


@pytest.mark.parametrize(
    ("model", "key"), [(Note, "note"), (ChatConversation, "conversation")]
)
def test_database_accepts_valid_same_owner_project_reference(
    ownership_case, model, key
):
    engine, ids = ownership_case
    with engine.begin() as db:
        db.execute(
            update(model)
            .where(model.id == ids[key])
            .values(project_id=ids["same_owner_project"])
        )
        assert (
            db.scalar(select(model.project_id).where(model.id == ids[key]))
            == ids["same_owner_project"]
        )


def test_project_owner_change_cannot_orphan_existing_children(ownership_case):
    engine, ids = ownership_case
    with pytest.raises(IntegrityError) as caught, engine.begin() as db:
        db.execute(
            update(Project)
            .where(Project.id == ids["project"])
            .values(user_id=ids["stranger"])
        )
    assert caught.value.orig.sqlstate == "23503"
    with engine.connect() as db:
        assert (
            db.scalar(select(Project.user_id).where(Project.id == ids["project"]))
            == ids["owner"]
        )


@pytest.mark.parametrize("parent", ["project", "user"])
def test_owner_constraints_preserve_deletion_cascades(ownership_case, parent):
    engine, ids = ownership_case
    second_note, message, job, connection, cleanup = (uuid4() for _ in range(5))
    with engine.begin() as db:
        db.execute(
            insert(Note).values(
                id=second_note,
                user_id=ids["owner"],
                project_id=ids["project"],
                content="Related",
            )
        )
        db.execute(
            insert(NoteConnection).values(
                id=connection, source_note_id=ids["note"], target_note_id=second_note
            )
        )
        db.execute(
            insert(NoteProcessingJob).values(id=job, note_id=ids["note"], revision=1)
        )
        db.execute(
            insert(ChatMessage).values(
                id=message,
                conversation_id=ids["conversation"],
                role="assistant",
                content="Answer",
            )
        )
        db.execute(
            insert(ChatMessageSource).values(message_id=message, note_id=ids["note"])
        )
        db.execute(insert(VectorCleanupRequest).values(id=cleanup, note_id=ids["note"]))
        if parent == "project":
            db.execute(delete(Project).where(Project.id == ids["project"]))
        else:
            db.execute(delete(User).where(User.id == ids["owner"]))
        for model, identity in (
            (Note, ids["note"]),
            (Note, second_note),
            (NoteConnection, connection),
            (NoteProcessingJob, job),
            (ChatConversation, ids["conversation"]),
            (ChatMessage, message),
        ):
            assert db.scalar(select(model.id).where(model.id == identity)) is None
        assert (
            db.scalar(
                select(ChatMessageSource.message_id).where(
                    ChatMessageSource.message_id == message
                )
            )
            is None
        )
        assert (
            db.scalar(
                select(VectorCleanupRequest.id).where(
                    VectorCleanupRequest.id == cleanup
                )
            )
            == cleanup
        )
        assert (
            db.scalar(select(Note.id).where(Note.id == ids["other_note"]))
            == ids["other_note"]
        )
        assert (
            db.scalar(
                select(ChatConversation.id).where(
                    ChatConversation.id == ids["other_conversation"]
                )
            )
            == ids["other_conversation"]
        )


def test_populated_migration_round_trip_preserves_records(postgres_engine):
    config = Config("alembic.ini")
    command.upgrade(config, PREVIOUS_REVISION)
    ids = seed_owners(postgres_engine)
    command.upgrade(config, "head")
    assert_ownership_constraints(postgres_engine)
    with postgres_engine.connect() as db:
        assert (
            db.scalar(select(Note.content).where(Note.id == ids["note"]))
            == "Owner content"
        )
        assert (
            db.scalar(
                select(ChatConversation.title).where(
                    ChatConversation.id == ids["conversation"]
                )
            )
            == "Owner chat"
        )
    command.downgrade(config, PREVIOUS_REVISION)
    for table in ("notes", "chat_conversations"):
        constraint = next(
            fk
            for fk in inspect(postgres_engine).get_foreign_keys(table)
            if fk["referred_table"] == "projects"
        )
        assert constraint["name"] == f"{table}_project_id_fkey"
        assert constraint["constrained_columns"] == ["project_id"]
        assert constraint["options"]["ondelete"] == "CASCADE"
    assert "uq_projects_id_user_id" not in {
        constraint["name"]
        for constraint in inspect(postgres_engine).get_unique_constraints("projects")
    }
    command.upgrade(config, "head")
    assert_ownership_constraints(postgres_engine)


@pytest.mark.parametrize("invalid_table", ["notes", "chat_conversations"])
def test_migration_aborts_on_invalid_legacy_data_without_repairing_it(
    postgres_engine, invalid_table
):
    config = Config("alembic.ini")
    command.upgrade(config, PREVIOUS_REVISION)
    ids = seed_owners(postgres_engine)
    invalid_id = uuid4()
    model = Note if invalid_table == "notes" else ChatConversation
    values = {
        "id": invalid_id,
        "user_id": ids["stranger"],
        "project_id": ids["project"],
    }
    if model is Note:
        values["content"] = (
            "Private fixture content must never appear in the preflight error"
        )
    with postgres_engine.begin() as db:
        db.execute(insert(model).values(**values))
    with pytest.raises(
        DBAPIError, match="Project ownership preflight failed"
    ) as caught:
        command.upgrade(config, "head")
    assert "Private fixture content" not in str(caught.value)
    with postgres_engine.connect() as db:
        row = db.execute(
            select(model.user_id, model.project_id).where(model.id == invalid_id)
        ).one()
        assert tuple(row) == (ids["stranger"], ids["project"])
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version"))
            == PREVIOUS_REVISION
        )
    assert "uq_projects_id_user_id" not in {
        constraint["name"]
        for constraint in inspect(postgres_engine).get_unique_constraints("projects")
    }


def test_offline_migration_sql_includes_preflight(postgres_engine):
    output = StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert "Project ownership preflight failed" in sql
    assert (
        "fk_notes_project_owner FOREIGN KEY(project_id, user_id) REFERENCES projects (id, user_id) ON DELETE CASCADE"
        in sql
    )
    assert (
        "fk_chat_conversations_project_owner FOREIGN KEY(project_id, user_id) REFERENCES projects (id, user_id) ON DELETE CASCADE"
        in sql
    )
