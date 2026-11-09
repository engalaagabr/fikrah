from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import get_db_session as database_dependency
from app.main import app as fastapi_app
from app.models.base import Base
import app.models  # noqa: F401


@pytest_asyncio.fixture
async def auth_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "test-signing-secret-that-is-at-least-32-characters")
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator:
        async with sessions() as session:
            yield session

    fastapi_app.dependency_overrides[database_dependency] = override_session
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client
    fastapi_app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_email_auth_verification_refresh_and_logout(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered: list[tuple[str, str, str]] = []

    async def capture_email(email: str, token: str, purpose: str) -> None:
        delivered.append((email, token, purpose))

    monkeypatch.setattr("app.auth.routes.send_action_email", capture_email)
    email = "Fikrah.User@example.com"
    password = "a secure passphrase with length"

    registration = await auth_client.post(
        "/v1/auth/register", json={"email": email, "password": password}
    )
    assert registration.status_code == 202
    assert delivered[0][0] == email.lower()
    assert delivered[0][2] == "verify_email"

    blocked_login = await auth_client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    assert blocked_login.status_code == 403

    verification = await auth_client.post(
        "/v1/auth/verify-email", json={"token": delivered[0][1]}
    )
    assert verification.status_code == 200
    replay = await auth_client.post(
        "/v1/auth/verify-email", json={"token": delivered[0][1]}
    )
    assert replay.status_code == 400

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")
    monkeypatch.setattr(
        "app.auth.routes.id_token.verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "linked-google-subject", "email": email.lower(), "email_verified": True
        },
    )
    linked_google_login = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-id-token-for-existing-account"}
    )
    assert linked_google_login.status_code == 200

    login = await auth_client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["expires_in"] == 900

    current_user = await auth_client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert current_user.status_code == 200
    assert current_user.json()["email"] == email.lower()
    assert current_user.json()["email_verified"] is True
    assert current_user.json()["id"] == (
        await auth_client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {linked_google_login.json()['access_token']}"},
        )
    ).json()["id"]

    rotated = await auth_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]
    reused = await auth_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401

    logout = await auth_client.post(
        "/v1/auth/logout", json={"refresh_token": rotated.json()["refresh_token"]}
    )
    assert logout.status_code == 200
    revoked = await auth_client.post(
        "/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}
    )
    assert revoked.status_code == 401


@pytest.mark.asyncio
async def test_google_login_requires_verified_email_and_issues_fikrah_tokens(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")

    def verify_google_token(token: str, request: object, audience: str) -> dict[str, object]:
        assert token == "google-id-token-from-mobile"
        assert audience == "mobile-client-id"
        return {"sub": "google-user-1", "email": "google.user@example.com", "email_verified": True}

    monkeypatch.setattr("app.auth.routes.id_token.verify_oauth2_token", verify_google_token)
    response = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-id-token-from-mobile"}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    me = await auth_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "google.user@example.com"
