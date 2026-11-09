from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token
from app.database import get_db_session
from app.main import app as fastapi_app
from app.models import Project, User
from app.models.base import Base


@pytest_asyncio.fixture
async def project_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, UUID, UUID, UUID, str, str]]:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "project-test-secret-that-is-at-least-32-characters")
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        now = datetime.now(timezone.utc)
        user = User(email="owner@example.com", email_verified_at=now)
        other_user = User(email="other@example.com", email_verified_at=now)
        session.add_all([user, other_user])
        await session.flush()
        general = Project(user_id=user.id, name="General", is_general=True)
        session.add_all([general, Project(user_id=other_user.id, name="General", is_general=True)])
        await session.commit()
        user_id, other_user_id, general_id = user.id, other_user.id, general.id

    async def override_session() -> AsyncIterator:
        async with sessions() as session:
            yield session

    fastapi_app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield (
            client,
            user_id,
            other_user_id,
            general_id,
            create_access_token(user_id),
            create_access_token(other_user_id),
        )
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_project_crud_and_user_isolation(
    project_api: tuple[AsyncClient, UUID, UUID, UUID, str, str]
) -> None:
    client, _, _, general_id, owner_token, other_token = project_api
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    created = await client.post("/v1/projects", headers=owner_headers, json={"name": "  Research  "})
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Research"
    assert project["is_general"] is False

    listed = await client.get("/v1/projects", headers=owner_headers)
    assert listed.status_code == 200
    assert [row["is_general"] for row in listed.json()] == [True, False]

    read = await client.get(f"/v1/projects/{project['id']}", headers=owner_headers)
    assert read.status_code == 200
    cross_user_read = await client.get(f"/v1/projects/{project['id']}", headers=other_headers)
    assert cross_user_read.status_code == 404

    renamed = await client.patch(
        f"/v1/projects/{project['id']}", headers=owner_headers, json={"name": "Knowledge"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Knowledge"

    deleted = await client.delete(f"/v1/projects/{project['id']}", headers=owner_headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/projects/{project['id']}", headers=owner_headers)).status_code == 404

    general_delete = await client.delete(f"/v1/projects/{general_id}", headers=owner_headers)
    assert general_delete.status_code == 409


@pytest.mark.asyncio
async def test_projects_require_auth_and_nonblank_names(
    project_api: tuple[AsyncClient, UUID, UUID, UUID, str, str]
) -> None:
    client, _, _, _, owner_token, _ = project_api

    assert (await client.get("/v1/projects")).status_code == 401
    blank_name = await client.post(
        "/v1/projects", headers={"Authorization": f"Bearer {owner_token}"}, json={"name": "   "}
    )
    assert blank_name.status_code == 422
