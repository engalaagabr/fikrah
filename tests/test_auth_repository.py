from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.service import _send_limit_available
from app.models import EmailSendAttempt
from app.models.base import Base


@pytest.mark.asyncio
async def test_email_send_limit_enforces_hourly_cap_and_cooldown() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    hourly_email = "hourly-limit@example.com"
    cooldown_email = "cooldown-limit@example.com"
    now = datetime.now(timezone.utc)
    async with sessions() as session:
        session.add_all(
            [
                EmailSendAttempt(
                    email=hourly_email,
                    created_at=now - timedelta(minutes=2),
                )
                for _ in range(5)
            ]
        )
        session.add(
            EmailSendAttempt(
                email=cooldown_email,
                created_at=now - timedelta(seconds=30),
            )
        )
        await session.commit()

        assert not await _send_limit_available(session, hourly_email)
        assert not await _send_limit_available(session, cooldown_email)
        attempts = list(await session.scalars(select(EmailSendAttempt)))
        assert len(attempts) == 6

    await engine.dispose()
