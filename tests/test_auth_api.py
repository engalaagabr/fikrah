from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import (
    get_db_session as database_dependency,
)
from app.main import app as fastapi_app


@pytest_asyncio.fixture
async def auth_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "test-signing-secret-that-is-at-least-32-characters"
    )
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
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
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

    welcomed: list[str] = []

    async def capture_welcome(email: str) -> None:
        welcomed.append(email)

    monkeypatch.setattr("app.infrastructure.container.auth_service.send_action_email", capture_email)
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.send_welcome_email", capture_welcome
    )
    email = "Fikrah.User@example.com"
    password = "a secure passphrase with length"

    registration = await auth_client.post(
        "/v1/auth/register", json={"email": email, "password": password}
    )
    assert registration.status_code == 202
    assert delivered[0][0] == email.lower()
    assert delivered[0][2] == "verify_email"
    assert welcomed == [email.lower()]

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
        "app.infrastructure.container.auth_service.verify_google_id_token",
        lambda token, audience: {
            "sub": "linked-google-subject",
            "email": email.lower(),
            "email_verified": True,
            "hd": "example.com",
        },
    )
    linked_google_login = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-id-token-for-existing-account"}
    )
    assert linked_google_login.status_code == 200
    assert welcomed == [email.lower()]

    login = await auth_client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["expires_in"] == 900

    current_user = await auth_client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert current_user.status_code == 200
    assert current_user.json()["email"] == email.lower()
    assert current_user.json()["email_verified"] is True
    assert (
        current_user.json()["id"]
        == (
            await auth_client.get(
                "/v1/auth/me",
                headers={
                    "Authorization": f"Bearer {linked_google_login.json()['access_token']}"
                },
            )
        ).json()["id"]
    )

    rotated = await auth_client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]
    reused = await auth_client.post(
        "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
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
async def test_google_link_discards_unverified_local_password(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered: list[str] = []

    async def capture_email(email: str, token: str, purpose: str) -> None:
        delivered.append(token)

    async def capture_welcome(email: str) -> None:
        pass

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.send_action_email", capture_email
    )
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.send_welcome_email", capture_welcome
    )
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.verify_google_id_token",
        lambda *_: {
            "sub": "actual-mailbox-owner",
            "email": "pre-registered@gmail.com",
            "email_verified": True,
            "hd": "example.com",
        },
    )
    credentials = {
        "email": "pre-registered@gmail.com",
        "password": "a password chosen by somebody else",
    }
    assert (await auth_client.post("/v1/auth/register", json=credentials)).status_code == 202
    assert (await auth_client.post("/v1/auth/login", json=credentials)).status_code == 403

    linked = await auth_client.post(
        "/v1/auth/google", json={"id_token": "verified-google-token-for-the-owner"}
    )
    assert linked.status_code == 200
    assert (await auth_client.post("/v1/auth/login", json=credentials)).status_code == 401
    assert (
        await auth_client.post("/v1/auth/verify-email", json={"token": delivered[0]})
    ).status_code == 400
    assert (
        await auth_client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {linked.json()['access_token']}"},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_google_login_requires_verified_email_and_issues_fikrah_tokens(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")

    def verify_google_token(token: str, audience: str) -> dict[str, object]:
        assert token == "google-id-token-from-mobile"
        assert audience == "mobile-client-id"
        return {
            "sub": "google-user-1",
            "email": "google.user@example.com",
            "email_verified": True,
            "hd": "example.com",
        }

    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.verify_google_id_token", verify_google_token
    )
    welcomed: list[str] = []

    async def capture_welcome(email: str) -> None:
        welcomed.append(email)

    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.send_welcome_email", capture_welcome
    )
    response = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-id-token-from-mobile"}
    )

    assert response.status_code == 200
    assert welcomed == ["google.user@example.com"]
    assert response.json()["access_token"]
    me = await auth_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "google.user@example.com"


@pytest.mark.asyncio
async def test_password_reset_revokes_existing_refresh_sessions(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered: list[tuple[str, str, str]] = []

    async def capture_email(email: str, token: str, purpose: str) -> None:
        delivered.append((email, token, purpose))

    async def allow_email_send(db, email: str, repository=None) -> bool:
        return True

    async def capture_welcome(email: str) -> None:
        return None

    monkeypatch.setattr("app.infrastructure.container.auth_service.send_action_email", capture_email)
    monkeypatch.setattr("app.infrastructure.container.auth_service.send_welcome_email", capture_welcome)
    monkeypatch.setattr("app.services.auth_service._send_limit_available", allow_email_send)

    email = "reset-user@example.com"
    old_password = "a secure passphrase before reset"
    new_password = "a secure passphrase after reset"
    registration = await auth_client.post(
        "/v1/auth/register", json={"email": email, "password": old_password}
    )
    assert registration.status_code == 202
    verification = await auth_client.post(
        "/v1/auth/verify-email", json={"token": delivered[0][1]}
    )
    assert verification.status_code == 200

    login = await auth_client.post(
        "/v1/auth/login", json={"email": email, "password": old_password}
    )
    assert login.status_code == 200
    old_refresh_token = login.json()["refresh_token"]

    requested = await auth_client.post(
        "/v1/auth/password-reset/request", json={"email": email}
    )
    assert requested.status_code == 202
    assert delivered[-1][2] == "reset_password"

    confirmed = await auth_client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": delivered[-1][1], "new_password": new_password},
    )
    assert confirmed.status_code == 200
    old_session_refresh = await auth_client.post(
        "/v1/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert old_session_refresh.status_code == 401

    old_password_login = await auth_client.post(
        "/v1/auth/login", json={"email": email, "password": old_password}
    )
    assert old_password_login.status_code == 401
    new_password_login = await auth_client.post(
        "/v1/auth/login", json={"email": email, "password": new_password}
    )
    assert new_password_login.status_code == 200


@pytest.mark.asyncio
async def test_resend_verification_replaces_previous_link(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered: list[tuple[str, str, str]] = []

    async def capture_email(email: str, token: str, purpose: str) -> None:
        delivered.append((email, token, purpose))

    async def capture_welcome(email: str) -> None:
        return None

    async def allow_email_send(db, email: str, repository=None) -> bool:
        return True

    monkeypatch.setattr("app.infrastructure.container.auth_service.send_action_email", capture_email)
    monkeypatch.setattr("app.infrastructure.container.auth_service.send_welcome_email", capture_welcome)
    monkeypatch.setattr("app.services.auth_service._send_limit_available", allow_email_send)

    email = "resend-user@example.com"
    registration = await auth_client.post(
        "/v1/auth/register",
        json={"email": email, "password": "a secure passphrase for resend"},
    )
    assert registration.status_code == 202

    resent = await auth_client.post(
        "/v1/auth/resend-verification", json={"email": email}
    )
    assert resent.status_code == 202
    assert len(delivered) == 2

    old_link = await auth_client.post(
        "/v1/auth/verify-email", json={"token": delivered[0][1]}
    )
    new_link = await auth_client.post(
        "/v1/auth/verify-email", json={"token": delivered[1][1]}
    )
    assert old_link.status_code == 400
    assert new_link.status_code == 200


@pytest.mark.asyncio
async def test_google_external_email_cannot_create_account(auth_client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.verify_google_id_token",
        lambda *_: {
            "sub": "untrusted-external-subject", "email": "outside@example.com",
            "email_verified": True,
        },
    )
    response = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-token-with-non-authoritative-email"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_previously_linked_subject_can_sign_in_without_email_authority(
    auth_client, monkeypatch
):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mobile-client-id")
    claims = {
        "sub": "previously-linked", "email": "linked@example.com",
        "email_verified": True, "hd": "example.com",
    }
    monkeypatch.setattr(
        "app.infrastructure.container.auth_service.verify_google_id_token",
        lambda *_: dict(claims),
    )
    async def welcome(_):
        pass
    monkeypatch.setattr("app.infrastructure.container.auth_service.send_welcome_email", welcome)
    first = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-token-for-the-linked-account"}
    )
    assert first.status_code == 200
    claims.pop("hd")
    second = await auth_client.post(
        "/v1/auth/google", json={"id_token": "google-token-for-the-linked-account"}
    )
    assert second.status_code == 200
