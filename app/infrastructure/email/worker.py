"""Worker composition for retrying durable email delivery intents."""

from datetime import datetime, timezone

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings, get_worker_settings
from app.infrastructure.email.cipher import reveal_email_token
from app.infrastructure.email.smtp import send_action_email, send_welcome_email
from app.repositories.email import EmailOutboxRepository
from app.services.email_delivery_service import EmailDeliveryService


async def deliver_pending_account_emails() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for email delivery")
    url = make_url(settings.database_url)
    if url.drivername.startswith("postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    elif url.drivername == "sqlite":
        url = url.set(drivername="sqlite+aiosqlite")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = EmailOutboxRepository()
    sender = EmailDeliveryService(
        send_action_email, send_welcome_email, reveal_email_token, repository
    )
    try:
        async with sessions() as db:
            ids = await repository.due_ids(
                db,
                datetime.now(timezone.utc),
                get_worker_settings().dispatch_batch_size,
            )
            await db.rollback()
            for delivery_id in ids:
                await sender.deliver(db, delivery_id)
    finally:
        await engine.dispose()
