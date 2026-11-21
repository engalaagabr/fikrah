"""Queries for email delivery claims and action-token validity."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailActionToken, EmailDelivery


class EmailOutboxRepository:
    async def add(self, db: AsyncSession, delivery: EmailDelivery) -> None:
        db.add(delivery)
        await db.flush()

    async def get_locked(
        self, db: AsyncSession, delivery_id: UUID
    ) -> EmailDelivery | None:
        return await db.scalar(
            select(EmailDelivery)
            .where(EmailDelivery.id == delivery_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )

    async def action_is_current(
        self, db: AsyncSession, delivery: EmailDelivery, now: datetime
    ) -> bool:
        return (
            await db.scalar(
                select(EmailActionToken.id).where(
                    EmailActionToken.token_hash == delivery.token_hash,
                    EmailActionToken.user_id == delivery.user_id,
                    EmailActionToken.purpose == delivery.purpose,
                    EmailActionToken.used_at.is_(None),
                    EmailActionToken.expires_at > now,
                )
            )
            is not None
        )

    async def due_ids(self, db: AsyncSession, now: datetime, limit: int) -> list[UUID]:
        return list(
            await db.scalars(
                select(EmailDelivery.id)
                .where(
                    EmailDelivery.sent_at.is_(None),
                    EmailDelivery.cancelled_at.is_(None),
                    EmailDelivery.next_attempt_at <= now,
                    or_(
                        EmailDelivery.claimed_at.is_(None),
                        EmailDelivery.claimed_at < now - timedelta(seconds=60),
                    ),
                )
                .order_by(EmailDelivery.created_at, EmailDelivery.id)
                .limit(limit)
            )
        )
