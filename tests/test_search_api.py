from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token
from app.database import get_db_session
from app.main import app as fastapi_app
from app.models import Note, Project, User
from app.models.base import Base


@pytest_asyncio.fixture
async def search_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], UUID, UUID, UUID, UUID, UUID, UUID, str]
]:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "search-test-secret-that-is-at-least-32-characters")
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        now = datetime.now(timezone.utc)
        owner = User(email="search-owner@example.com", email_verified_at=now)
        other = User(email="search-other@example.com", email_verified_at=now)
        session.add_all([owner, other])
        await session.flush()
        project = Project(user_id=owner.id, name="Research")
        other_project = Project(user_id=other.id, name="Private")
        session.add_all([project, other_project])
        await session.flush()
        current = Note(
            user_id=owner.id,
            project_id=project.id,
            title="Current result",
            content="The current project note.",
            revision=2,
            processing_status="completed",
        )
        stale = Note(
            user_id=owner.id,
            project_id=project.id,
            content="A note whose indexed revision is stale.",
            revision=2,
            processing_status="completed",
        )
        queued = Note(
            user_id=owner.id,
            project_id=project.id,
            content="A note still processing.",
            processing_status="processing",
        )
        private = Note(
            user_id=other.id,
            project_id=other_project.id,
            content="Another user's note.",
            processing_status="completed",
        )
        session.add_all([current, stale, queued, private])
        await session.commit()
        await session.refresh(current)
        owner_id, other_project_id, project_id = owner.id, other_project.id, project.id
        current_id, stale_id, queued_id, private_id = current.id, stale.id, queued.id, private.id

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    fastapi_app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        yield (
            client,
            sessions,
            owner_id,
            other_project_id,
            project_id,
            current_id,
            stale_id,
            queued_id,
            private_id,
            create_access_token(owner_id),
        )
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.1, 0.2]


@pytest.mark.asyncio
async def test_search_returns_only_authorized_current_completed_notes(
    search_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.search import service

    client, _, owner_id, _, project_id, current_id, stale_id, queued_id, private_id, token = search_api
    embedding = FakeEmbeddingModel()
    calls: list[tuple[object, ...]] = []

    class Factory:
        @staticmethod
        def create_embedding_model() -> FakeEmbeddingModel:
            return embedding

    def find_vectors(
        vector: list[float], user_id: UUID, scope_id: UUID, limit: int
    ) -> list[tuple[UUID, int, float]]:
        calls.append((vector, user_id, scope_id, limit))
        return [
            (current_id, 2, 0.93),
            (stale_id, 1, 0.89),
            (queued_id, 1, 0.82),
            (private_id, 1, 0.80),
        ]

    monkeypatch.setattr(service, "AIProviderFactory", Factory)
    monkeypatch.setattr(service, "search_note_vectors", find_vectors)

    response = await client.post(
        f"/v1/projects/{project_id}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "  where did I leave the idea?  "},
    )

    assert response.status_code == 200
    assert [item["note_id"] for item in response.json()] == [str(current_id)]
    assert response.json()[0]["score"] == pytest.approx(0.93)
    assert embedding.queries == ["where did I leave the idea?"]
    assert calls == [([0.1, 0.2], owner_id, project_id, 10)]


@pytest.mark.asyncio
async def test_search_is_scoped_to_the_authenticated_user_and_selected_project(
    search_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.search import service

    client, _, _, other_project_id, _, _, _, _, _, token = search_api

    def unexpected_search(*args: object) -> list[tuple[UUID, int, float]]:
        raise AssertionError("Qdrant must not be queried for another user's project")

    monkeypatch.setattr(service, "search_note_vectors", unexpected_search)
    response = await client.post(
        f"/v1/projects/{other_project_id}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "private"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_rejects_blank_queries(search_api) -> None:
    client, _, _, _, project_id, _, _, _, _, token = search_api
    response = await client.post(
        f"/v1/projects/{project_id}/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "   "},
    )
    assert response.status_code == 422
