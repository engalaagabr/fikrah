"""Durable account-email recovery and encrypted token payload checks."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_opaque_token
from app.db.base import Base
from app.infrastructure.email.cipher import protect_email_token, reveal_email_token
from app.models import EmailActionToken, EmailDelivery
from app.services.auth_ports import EmailDeliveryError
from app.services.auth_service import AuthService
from app.services.contracts.auth import ActionToken, EmailPassword, GoogleIdentityToken
from app.services.email_delivery_service import EmailDeliveryService


@pytest_asyncio.fixture
async def outbox_case(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "outbox-test-private-secret-at-least-32-characters"
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    state = {"available": False, "actions": [], "welcomes": [], "db": None}

    async def action(email, token, purpose):
        assert not state["db"].in_transaction()
        if not state["available"]:
            raise EmailDeliveryError
        state["actions"].append((email, token, purpose))

    async def welcome(email):
        assert not state["db"].in_transaction()
        if not state["available"]:
            raise EmailDeliveryError
        state["welcomes"].append(email)

    auth = AuthService(
        send_action_email=action,
        send_welcome_email=welcome,
        protect_email_token=protect_email_token,
        reveal_email_token=reveal_email_token,
        google_client_id=lambda: "test-client",
        verify_google_id_token=lambda *_: {
            "sub": "google-outbox",
            "email": "outbox@gmail.com",
            "email_verified": True,
        },
    )
    sender = EmailDeliveryService(action, welcome, reveal_email_token)
    try:
        yield sessions, auth, sender, state
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_smtp_outage_preserves_account_and_recovers_encrypted_emails(outbox_case):
    sessions, auth, sender, state = outbox_case
    async with sessions() as db:
        state["db"] = db
        result = await auth.register(
            EmailPassword(
                email="durable@example.com",
                password="an email outbox safe test password",
            ),
            db,
        )
        assert "verification" in result.message
        rows = list(await db.scalars(select(EmailDelivery)))
        assert len(rows) == 2
        action = next(row for row in rows if row.purpose == "verify_email")
        raw_token = reveal_email_token(action.encrypted_token)
        assert raw_token not in action.encrypted_token
        assert hash_opaque_token(raw_token) == action.token_hash
        for row in rows:
            assert row.sent_at is None
            assert row.attempt_count == 1
            row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        ids = [row.id for row in rows]
        await db.commit()
        state["available"] = True
        for delivery_id in ids:
            assert await sender.deliver(db, delivery_id)
            assert not await sender.deliver(db, delivery_id)
        assert state["actions"] == [("durable@example.com", raw_token, "verify_email")]
        assert state["welcomes"] == ["durable@example.com"]
        assert (
            await auth.verify_email(ActionToken(token=raw_token), db)
        ).message == "Email verified"
        rows = list(await db.scalars(select(EmailDelivery)))
        assert all(
            row.encrypted_token is None and row.sent_at is not None for row in rows
        )


@pytest.mark.asyncio
async def test_outbox_does_not_send_retired_action_link(outbox_case):
    sessions, auth, sender, state = outbox_case
    async with sessions() as db:
        state["db"] = db
        await auth.register(
            EmailPassword(
                email="retired@example.com",
                password="another safe outbox test password",
            ),
            db,
        )
        action = await db.scalar(select(EmailActionToken))
        action.used_at = datetime.now(timezone.utc)
        delivery = await db.scalar(
            select(EmailDelivery).where(EmailDelivery.purpose == "verify_email")
        )
        delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        delivery_id = delivery.id
        await db.commit()
        state["available"] = True
        assert not await sender.deliver(db, delivery_id)
        assert state["actions"] == []
        await db.refresh(delivery)
        assert delivery.cancelled_at is not None
        assert delivery.encrypted_token is None


@pytest.mark.asyncio
async def test_google_login_succeeds_when_welcome_email_is_deferred(outbox_case):
    sessions, auth, _, state = outbox_case
    async with sessions() as db:
        state["db"] = db
        tokens = await auth.google_login(
            GoogleIdentityToken(id_token="verified-google-token"), db
        )
        assert tokens.access_token
        delivery = await db.scalar(select(EmailDelivery))
        assert delivery.purpose == "welcome"
        assert delivery.sent_at is None
