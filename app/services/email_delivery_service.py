"""Claim, send and record retryable account emails without SMTP under DB locks."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.email import EmailOutboxRepository
from app.services.auth_ports import EmailDeliveryError

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class EmailDeliveryService:
    def __init__(
        self,
        send_action_email: Callable[[str, str, str], Awaitable[None]],
        send_welcome_email: Callable[[str], Awaitable[None]],
        reveal_token: Callable[[str], str],
        repository: EmailOutboxRepository | None = None,
    ) -> None:
        self._send_action = send_action_email
        self._send_welcome = send_welcome_email
        self._reveal = reveal_token
        self._repository = repository or EmailOutboxRepository()

    async def deliver(self, db: AsyncSession, delivery_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        claim_token = uuid4()
        async with db.begin():
            delivery = await self._repository.get_locked(db, delivery_id)
            if (
                delivery is None
                or delivery.sent_at is not None
                or delivery.cancelled_at is not None
            ):
                return False
            if _utc(delivery.next_attempt_at) > now or (
                delivery.claimed_at is not None
                and _utc(delivery.claimed_at) > now - timedelta(seconds=60)
            ):
                return False
            if (
                delivery.purpose != "welcome"
                and not await self._repository.action_is_current(db, delivery, now)
            ):
                delivery.cancelled_at = now
                delivery.encrypted_token = None
                return False
            delivery.claim_token = claim_token
            delivery.claimed_at = now
            delivery.attempt_count += 1
            recipient, purpose, encrypted = (
                delivery.recipient,
                delivery.purpose,
                delivery.encrypted_token,
            )

        success = False
        try:
            if purpose == "welcome":
                await self._send_welcome(recipient)
            elif encrypted is not None:
                await self._send_action(recipient, self._reveal(encrypted), purpose)
            else:
                raise EmailDeliveryError
            success = True
        except EmailDeliveryError:
            logger.warning(
                "Account email deferred: delivery=%s purpose=%s", delivery_id, purpose
            )

        async with db.begin():
            delivery = await self._repository.get_locked(db, delivery_id)
            if delivery is None or delivery.claim_token != claim_token:
                return False
            delivery.claim_token = None
            delivery.claimed_at = None
            if success:
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.encrypted_token = None
            else:
                delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(30 * 2 ** min(delivery.attempt_count, 7), 3600)
                )
        return success
