"""Create real revocable sessions for resource-authorization fixtures."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.core.security import create_access_token, hash_opaque_token
from app.models import RefreshSession


async def seed_access_token(sessions, user_id: UUID) -> str:
    async with sessions() as db:
        session = RefreshSession(
            user_id=user_id,
            token_hash=hash_opaque_token(str(uuid4())),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(session)
        await db.commit()
        return create_access_token(user_id, session.family_id)
