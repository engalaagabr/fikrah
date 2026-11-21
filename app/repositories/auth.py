"""SQLAlchemy account, action-token, and refresh-session queries."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailActionToken, EmailSendAttempt, Project, RefreshSession, User


class AuthRepository:
    async def lock_account_creation(
        self, db: AsyncSession, email: str, google_subject: str | None = None
    ) -> None:
        if db.get_bind().dialect.name != "postgresql":
            return
        identities = {f"email:{email}"}
        if google_subject is not None:
            identities.add(f"google:{google_subject}")
        for identity in sorted(identities):
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 74192039))"),
                {"identity": identity},
            )

    async def add_user(self, db: AsyncSession, user: User) -> None:
        db.add(user)
        await db.flush()

    def add_project(self, db: AsyncSession, project: Project) -> None:
        db.add(project)

    async def lock_email_send_attempts(
        self, db: AsyncSession, email: str
    ) -> None:
        if db.get_bind().dialect.name == "postgresql":
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 74192038))"),
                {"email": email},
            )

    async def count_recent_email_send_attempts(
        self, db: AsyncSession, email: str, since: datetime
    ) -> int | None:
        return await db.scalar(
            select(func.count(EmailSendAttempt.id)).where(
                EmailSendAttempt.email == email,
                EmailSendAttempt.created_at >= since,
            )
        )

    async def latest_email_send_attempt(
        self, db: AsyncSession, email: str
    ) -> datetime | None:
        return await db.scalar(
            select(EmailSendAttempt.created_at)
            .where(EmailSendAttempt.email == email)
            .order_by(EmailSendAttempt.created_at.desc())
            .limit(1)
        )

    async def add_email_send_attempt(self, db: AsyncSession, email: str) -> None:
        db.add(EmailSendAttempt(email=email))
        await db.flush()

    async def retire_open_action_tokens(
        self,
        db: AsyncSession,
        user_id: UUID,
        purpose: str,
        used_at: datetime,
    ) -> None:
        await db.execute(
            update(EmailActionToken)
            .where(
                EmailActionToken.user_id == user_id,
                EmailActionToken.purpose == purpose,
                EmailActionToken.used_at.is_(None),
            )
            .values(used_at=used_at)
        )

    async def add_action_token(
        self, db: AsyncSession, action_token: EmailActionToken
    ) -> None:
        db.add(action_token)
        await db.flush()

    async def find_user_id_by_email(
        self, db: AsyncSession, email: str
    ) -> UUID | None:
        return await db.scalar(select(User.id).where(User.email == email))

    async def find_action_token(
        self, db: AsyncSession, token_hash: str, purpose: str
    ) -> EmailActionToken | None:
        return await db.scalar(
            select(EmailActionToken)
            .where(
                EmailActionToken.token_hash == token_hash,
                EmailActionToken.purpose == purpose,
            )
            .with_for_update()
        )

    async def find_user_by_email(
        self, db: AsyncSession, email: str, *, lock: bool = False
    ) -> User | None:
        query = select(User).where(User.email == email)
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def find_user_by_google_subject(
        self, db: AsyncSession, subject: object
    ) -> User | None:
        return await db.scalar(
            select(User).where(User.google_subject == subject).with_for_update()
        )

    async def get_user(self, db: AsyncSession, user_id: UUID) -> User | None:
        return await db.get(User, user_id)

    async def add_refresh_session(
        self, db: AsyncSession, refresh_session: RefreshSession
    ) -> None:
        db.add(refresh_session)
        await db.flush()

    async def find_refresh_session(
        self, db: AsyncSession, token_hash: str, *, lock: bool = False
    ) -> RefreshSession | None:
        query = select(RefreshSession).where(
            RefreshSession.token_hash == token_hash
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def revoke_active_refresh_sessions(
        self, db: AsyncSession, user_id: UUID, revoked_at: datetime
    ) -> None:
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
