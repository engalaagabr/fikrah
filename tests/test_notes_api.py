from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token
from app.database import get_db_session
from app.main import app as fastapi_app
from app.models import (
    Note,
    NoteConnection,
    NoteIdempotencyKey,
    NoteProcessingJob,
    Project,
    User,
    VectorCleanupRequest,
)
from app.models.base import Base


@pytest_asyncio.fixture
async def note_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]]:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "note-test-secret-that-is-at-least-32-characters")
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        now = datetime.now(timezone.utc)
        owner = User(email="notes-owner@example.com", email_verified_at=now)
        other = User(email="notes-other@example.com", email_verified_at=now)
        session.add_all([owner, other])
        await session.flush()
        project = Project(user_id=owner.id, name="Research", is_general=False)
        other_project = Project(user_id=other.id, name="Private", is_general=False)
        session.add_all([project, other_project])
        await session.commit()
        owner_id, other_id = owner.id, other.id
        project_id, other_project_id = project.id, other_project.id

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    fastapi_app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield (
            client,
            sessions,
            owner_id,
            other_id,
            project_id,
            other_project_id,
            create_access_token(owner_id),
            create_access_token(other_id),
        )
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_note_create_retry_update_poll_and_delete(
    note_api: tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]
) -> None:
    client, sessions, _, _, project_id, _, owner_token, _ = note_api
    headers = {"Authorization": f"Bearer {owner_token}", "Idempotency-Key": "same-capture-1"}

    created = await client.post(
        f"/v1/projects/{project_id}/notes",
        headers=headers,
        json={"content": "  A thought to remember.  "},
    )
    assert created.status_code == 201
    note = created.json()
    assert note["content"] == "A thought to remember."
    assert note["title"] is None
    assert note["revision"] == 1
    assert note["processing_status"] == "queued"

    retried = await client.post(
        f"/v1/projects/{project_id}/notes",
        headers=headers,
        json={"content": "A thought to remember."},
    )
    assert retried.status_code == 201
    assert retried.json()["id"] == note["id"]
    mismatch = await client.post(
        f"/v1/projects/{project_id}/notes",
        headers=headers,
        json={"content": "A different thought."},
    )
    assert mismatch.status_code == 409

    listed = await client.get(f"/v1/projects/{project_id}/notes", headers=headers)
    assert [row["id"] for row in listed.json()] == [note["id"]]
    fetched = await client.get(f"/v1/notes/{note['id']}", headers=headers)
    assert fetched.status_code == 200

    updated = await client.patch(
        f"/v1/notes/{note['id']}", headers=headers, json={"content": "Updated thought"}
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["processing_status"] == "queued"
    retry = await client.post(f"/v1/notes/{note['id']}/processing-retries", headers=headers)
    assert retry.status_code == 202
    assert retry.json()["revision"] == 2
    assert retry.json()["processing_generation"] == 3

    deleted = await client.delete(f"/v1/notes/{note['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/notes/{note['id']}", headers=headers)).status_code == 404
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(VectorCleanupRequest)) == 1
        assert await session.scalar(select(func.count()).select_from(NoteProcessingJob)) == 0


@pytest.mark.asyncio
async def test_note_access_is_scoped_to_user_and_project(
    note_api: tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]
) -> None:
    client, _, _, _, project_id, other_project_id, owner_token, other_token = note_api
    owner = {"Authorization": f"Bearer {owner_token}", "Idempotency-Key": "private-note"}
    other = {"Authorization": f"Bearer {other_token}", "Idempotency-Key": "other-note"}

    assert (await client.get(f"/v1/projects/{project_id}/notes", headers=other)).status_code == 404
    assert (
        await client.post(
            f"/v1/projects/{other_project_id}/notes", headers=owner, json={"content": "hidden"}
        )
    ).status_code == 404

    created = await client.post(
        f"/v1/projects/{project_id}/notes", headers=owner, json={"content": "private"}
    )
    note_id = created.json()["id"]
    assert (await client.get(f"/v1/notes/{note_id}", headers=other)).status_code == 404
    assert (await client.patch(f"/v1/notes/{note_id}", headers=other, json={"title": "leak"})).status_code == 404
    assert (await client.delete(f"/v1/notes/{note_id}", headers=other)).status_code == 404
    assert (
        await client.post(
            f"/v1/notes/{note_id}/refinement-regenerations",
            headers=other,
            json={"expected_processing_generation": 1},
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_refinement_can_be_accepted_rejected_or_regenerated(
    note_api: tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]
) -> None:
    client, sessions, _, _, project_id, _, owner_token, _ = note_api
    headers = {
        "Authorization": f"Bearer {owner_token}",
        "Idempotency-Key": "refinement-flow",
    }
    created = await client.post(
        f"/v1/projects/{project_id}/notes",
        headers=headers,
        json={"content": "Original note"},
    )
    note_id = created.json()["id"]
    async with sessions() as session:
        note = await session.get(Note, UUID(note_id))
        assert note is not None
        note.processing_status = "completed"
        note.refinement_proposal = "Clearer note"
        await session.commit()

    regenerated = await client.post(
        f"/v1/notes/{note_id}/refinement-regenerations",
        headers=headers,
        json={"expected_processing_generation": 1},
    )
    assert regenerated.status_code == 202
    assert regenerated.json()["content"] == "Original note"
    assert regenerated.json()["refinement_proposal"] is None
    assert regenerated.json()["processing_generation"] == 2
    assert regenerated.json()["revision"] == 1

    stale_reject = await client.post(
        f"/v1/notes/{note_id}/refinement-rejections",
        headers=headers,
        json={"expected_processing_generation": 1},
    )
    assert stale_reject.status_code == 409

    async with sessions() as session:
        note = await session.get(Note, UUID(note_id))
        assert note is not None
        note.processing_status = "completed"
        note.refinement_proposal = "A second wording"
        await session.commit()

    rejected = await client.post(
        f"/v1/notes/{note_id}/refinement-rejections",
        headers=headers,
        json={"expected_processing_generation": 2},
    )
    assert rejected.status_code == 200
    assert rejected.json()["refinement_proposal"] is None
    assert rejected.json()["content"] == "Original note"

    async with sessions() as session:
        note = await session.get(Note, UUID(note_id))
        assert note is not None
        note.refinement_proposal = "Accepted wording"
        await session.commit()

    accepted = await client.post(
        f"/v1/notes/{note_id}/refinement-acceptance",
        headers=headers,
        json={"expected_processing_generation": 2},
    )
    assert accepted.status_code == 200
    assert accepted.json()["content"] == "Accepted wording"
    assert accepted.json()["refinement_proposal"] is None
    assert accepted.json()["revision"] == 2
    assert accepted.json()["processing_generation"] == 3
    assert accepted.json()["processing_status"] == "queued"

    async with sessions() as session:
        jobs = await session.scalars(
            select(NoteProcessingJob).where(NoteProcessingJob.note_id == UUID(note_id))
        )
        assert sorted(job.processing_generation for job in jobs) == [1, 2, 3]


@pytest.mark.asyncio
async def test_editing_note_content_clears_proposal_for_previous_text(
    note_api: tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]
) -> None:
    client, sessions, _, _, project_id, _, owner_token, _ = note_api
    headers = {
        "Authorization": f"Bearer {owner_token}",
        "Idempotency-Key": "clear-old-proposal",
    }
    created = await client.post(
        f"/v1/projects/{project_id}/notes", headers=headers, json={"content": "Old content"}
    )
    note_id = created.json()["id"]
    async with sessions() as session:
        note = await session.get(Note, UUID(note_id))
        assert note is not None
        note.refinement_proposal = "Rewrite of old content"
        note.processing_status = "completed"
        await session.commit()

    updated = await client.patch(
        f"/v1/notes/{note_id}", headers=headers, json={"content": "New content"}
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "New content"
    assert updated.json()["refinement_proposal"] is None
    assert updated.json()["processing_generation"] == 2


@pytest.mark.asyncio
async def test_project_deletion_removes_notes_connections_and_records_vector_cleanup(
    note_api: tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, str, str]
) -> None:
    client, sessions, _, _, project_id, _, owner_token, _ = note_api
    headers = {"Authorization": f"Bearer {owner_token}"}
    note_ids: list[UUID] = []
    for index in range(2):
        response = await client.post(
            f"/v1/projects/{project_id}/notes",
            headers={**headers, "Idempotency-Key": f"delete-note-{index}"},
            json={"content": f"content {index}"},
        )
        assert response.status_code == 201
        note_ids.append(UUID(response.json()["id"]))
    async with sessions() as session:
        session.add(NoteConnection(source_note_id=note_ids[0], target_note_id=note_ids[1]))
        await session.commit()

    deleted = await client.delete(f"/v1/projects/{project_id}", headers=headers)
    assert deleted.status_code == 204
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Note).where(Note.id.in_(note_ids))) == 0
        assert await session.scalar(select(func.count()).select_from(NoteConnection)) == 0
        assert await session.scalar(select(func.count()).select_from(NoteProcessingJob)) == 0
        assert await session.scalar(select(func.count()).select_from(VectorCleanupRequest)) == 2
        # A retry cannot silently recreate content after project deletion.
        assert await session.scalar(select(func.count()).select_from(NoteIdempotencyKey)) == 2
