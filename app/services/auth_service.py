"""Authentication application workflows and account lifecycle use cases."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    REFRESH_TOKEN_TTL,
    create_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.models import EmailActionToken, Project, RefreshSession, User
from app.repositories.auth import AuthRepository
from app.services.auth_errors import AuthServiceError
from app.services.auth_ports import EmailDeliveryError, GoogleIdentityTokenError
from app.services.contracts.auth import (
    ActionToken,
    AuthMessage,
    AuthTokenPair,
    EmailAddress,
    EmailPassword,
    GoogleIdentityToken,
    PasswordReset,
    RefreshToken,
)

SendActionEmail = Callable[[str, str, str], Awaitable[None]]
SendWelcomeEmail = Callable[[str], Awaitable[None]]
VerifyGoogleIdToken = Callable[[str, str], dict[str, object]]
GoogleClientId = Callable[[], str | None]


def _auth_error(
    code: int, message: str, *, headers: dict[str, str] | None = None
) -> AuthServiceError:
    return AuthServiceError(code, message, headers=headers)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _send_limit_available(
    db: AsyncSession,
    email: str,
    repository: AuthRepository | None = None,
) -> bool:
    repository = repository or AuthRepository()
    now = datetime.now(timezone.utc)
    await repository.lock_email_send_attempts(db, email)
    recent = await repository.count_recent_email_send_attempts(
        db, email, now - timedelta(hours=1)
    )
    last = await repository.latest_email_send_attempt(db, email)
    if recent is not None and recent >= 5:
        return False
    if last is not None:
        # SQLite may return naive values in tests; PostgreSQL returns timezone-aware timestamps.
        last = _utc(last)
        if last > now - timedelta(seconds=60):
            return False
    await repository.add_email_send_attempt(db, email)
    return True


async def _new_action_token(
    db: AsyncSession,
    user: User,
    purpose: str,
    lifetime: timedelta,
    repository: AuthRepository,
) -> str:
    now = datetime.now(timezone.utc)
    await repository.retire_open_action_tokens(db, user.id, purpose, now)
    raw = new_opaque_token()
    await repository.add_action_token(
        db,
        EmailActionToken(
            user_id=user.id,
            token_hash=hash_opaque_token(raw),
            purpose=purpose,
            expires_at=now + lifetime,
        )
    )
    return raw


async def _issue_session(
    db: AsyncSession, user: User, repository: AuthRepository
) -> AuthTokenPair:
    refresh = new_opaque_token()
    await repository.add_refresh_session(
        db,
        RefreshSession(
            user_id=user.id,
            token_hash=hash_opaque_token(refresh),
            expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
        )
    )
    return AuthTokenPair(
        access_token=create_access_token(user.id), refresh_token=refresh
    )


class AuthService:
    """Authentication use cases with provider capabilities supplied at composition."""

    def __init__(
        self,
        *,
        send_action_email: SendActionEmail,
        send_welcome_email: SendWelcomeEmail,
        verify_google_id_token: VerifyGoogleIdToken,
        google_client_id: GoogleClientId,
        repository: AuthRepository | None = None,
    ) -> None:
        self.send_action_email = send_action_email
        self.send_welcome_email = send_welcome_email
        self.verify_google_id_token = verify_google_id_token
        self.google_client_id = google_client_id
        self._repository = repository or AuthRepository()

    async def register(self, body: EmailPassword, db: AsyncSession) -> AuthMessage:
        raw_token: str | None = None
        async with db.begin():
            existing_user_id = await self._repository.find_user_id_by_email(
                db, body.email
            )
            if existing_user_id is None and await _send_limit_available(
                db, body.email, self._repository
            ):
                user = User(
                    email=body.email,
                    password_hash=await asyncio.to_thread(hash_password, body.password),
                )
                await self._repository.add_user(db, user)
                self._repository.add_project(
                    db, Project(user_id=user.id, name="General", is_general=True)
                )
                raw_token = await _new_action_token(
                    db, user, "verify_email", timedelta(hours=24), self._repository
                )
        if raw_token is not None:
            try:
                await self.send_action_email(body.email, raw_token, "verify_email")
                await self.send_welcome_email(body.email)
            except EmailDeliveryError as exc:
                raise _auth_error(
                    503, "Email delivery is temporarily unavailable"
                ) from exc
        return AuthMessage(
            message="If the address can be registered, a verification email will be sent."
        )

    async def verify_email(self, body: ActionToken, db: AsyncSession) -> AuthMessage:
        now = datetime.now(timezone.utc)
        async with db.begin():
            action = await self._repository.find_action_token(
                db, hash_opaque_token(body.token), "verify_email"
            )
            if (
                action is None
                or action.used_at is not None
                or _utc(action.expires_at) <= now
            ):
                raise _auth_error(400, "The verification link is invalid or expired")
            action.used_at = now
            user = await self._repository.get_user(db, action.user_id)
            if user is None:
                raise _auth_error(400, "The verification link is invalid or expired")
            user.email_verified_at = now
        return AuthMessage(message="Email verified")

    async def resend_verification(
        self, body: EmailAddress, db: AsyncSession
    ) -> AuthMessage:
        raw_token: str | None = None
        async with db.begin():
            user = await self._repository.find_user_by_email(
                db, body.email, lock=True
            )
            if (
                user is not None
                and user.email_verified_at is None
                and await _send_limit_available(db, body.email, self._repository)
            ):
                raw_token = await _new_action_token(
                    db, user, "verify_email", timedelta(hours=24), self._repository
                )
        if raw_token is not None:
            try:
                await self.send_action_email(body.email, raw_token, "verify_email")
            except EmailDeliveryError as exc:
                raise _auth_error(
                    503, "Email delivery is temporarily unavailable"
                ) from exc
        return AuthMessage(
            message="If the address needs verification, an email will be sent."
        )

    async def login(self, body: EmailPassword, db: AsyncSession) -> AuthTokenPair:
        user = await self._repository.find_user_by_email(db, body.email)
        if user is None or user.password_hash is None:
            await asyncio.to_thread(verify_password, body.password, DUMMY_PASSWORD_HASH)
            raise _auth_error(
                401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
            )
        if not await asyncio.to_thread(
            verify_password, body.password, user.password_hash
        ):
            raise _auth_error(
                401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
            )
        if user.email_verified_at is None:
            raise _auth_error(403, "Verify your email before signing in")
        tokens = await _issue_session(db, user, self._repository)
        await db.commit()
        return tokens

    async def google_login(
        self, body: GoogleIdentityToken, db: AsyncSession
    ) -> AuthTokenPair:
        audience = self.google_client_id()
        if not audience:
            raise _auth_error(503, "Google sign-in is not configured")
        try:
            claims = await asyncio.to_thread(
                self.verify_google_id_token, body.id_token, audience
            )
        except GoogleIdentityTokenError:
            raise _auth_error(401, "Invalid Google ID token")
        email = str(claims.get("email", "")).strip().lower()
        subject = claims.get("sub")
        if not email or not subject or claims.get("email_verified") is not True:
            raise _auth_error(401, "Google account must have a verified email")

        created_user = False
        async with db.begin():
            subject_user = await self._repository.find_user_by_google_subject(
                db, subject
            )
            user = await self._repository.find_user_by_email(
                db, email, lock=True
            )
            if subject_user is not None and subject_user.email != email:
                raise _auth_error(
                    409, "The Google identity is linked to a different email address"
                )
            if user is None:
                created_user = True
                user = User(
                    email=email,
                    google_subject=subject,
                    email_verified_at=datetime.now(timezone.utc),
                )
                await self._repository.add_user(db, user)
                self._repository.add_project(
                    db, Project(user_id=user.id, name="General", is_general=True)
                )
            elif user.google_subject not in (None, subject):
                raise _auth_error(
                    409, "This account is linked to a different Google identity"
                )
            else:
                if user.email_verified_at is None:
                    # Establishing mailbox ownership must not activate a password
                    # chosen by whoever originally registered this address.
                    user.password_hash = None
                    now = datetime.now(timezone.utc)
                    for purpose in ("verify_email", "reset_password"):
                        await self._repository.retire_open_action_tokens(
                            db, user.id, purpose, now
                        )
                user.google_subject = subject
                user.email_verified_at = user.email_verified_at or datetime.now(
                    timezone.utc
                )
            tokens = await _issue_session(db, user, self._repository)
        if created_user:
            try:
                await self.send_welcome_email(email)
            except EmailDeliveryError as exc:
                raise _auth_error(
                    503, "Email delivery is temporarily unavailable"
                ) from exc
        return tokens

    async def request_password_reset(
        self, body: EmailAddress, db: AsyncSession
    ) -> AuthMessage:
        raw_token: str | None = None
        async with db.begin():
            user = await self._repository.find_user_by_email(
                db, body.email, lock=True
            )
            if (
                user is not None
                and user.password_hash is not None
                and await _send_limit_available(db, body.email, self._repository)
            ):
                raw_token = await _new_action_token(
                    db, user, "reset_password", timedelta(hours=1), self._repository
                )
        if raw_token is not None:
            try:
                await self.send_action_email(body.email, raw_token, "reset_password")
            except EmailDeliveryError as exc:
                raise _auth_error(
                    503, "Email delivery is temporarily unavailable"
                ) from exc
        return AuthMessage(
            message="If the account exists, a password reset email will be sent."
        )

    async def confirm_password_reset(
        self, body: PasswordReset, db: AsyncSession
    ) -> AuthMessage:
        now = datetime.now(timezone.utc)
        async with db.begin():
            action = await self._repository.find_action_token(
                db, hash_opaque_token(body.token), "reset_password"
            )
            if (
                action is None
                or action.used_at is not None
                or _utc(action.expires_at) <= now
            ):
                raise _auth_error(400, "The password reset link is invalid or expired")
            action.used_at = now
            user = await self._repository.get_user(db, action.user_id)
            if user is None:
                raise _auth_error(400, "The password reset link is invalid or expired")
            user.password_hash = await asyncio.to_thread(
                hash_password, body.new_password
            )
            await self._repository.revoke_active_refresh_sessions(
                db, user.id, now
            )
        return AuthMessage(message="Password reset successfully")

    async def refresh(self, body: RefreshToken, db: AsyncSession) -> AuthTokenPair:
        now = datetime.now(timezone.utc)
        async with db.begin():
            previous = await self._repository.find_refresh_session(
                db, hash_opaque_token(body.refresh_token), lock=True
            )
            if (
                previous is None
                or previous.revoked_at is not None
                or _utc(previous.expires_at) <= now
            ):
                raise _auth_error(401, "Invalid or expired refresh token")
            user = await self._repository.get_user(db, previous.user_id)
            if user is None:
                raise _auth_error(401, "Invalid or expired refresh token")
            tokens = await _issue_session(db, user, self._repository)
            replacement = await self._repository.find_refresh_session(
                db, hash_opaque_token(tokens.refresh_token)
            )
            previous.revoked_at = now
            previous.replaced_by_id = replacement.id
        return tokens

    async def logout(self, body: RefreshToken, db: AsyncSession) -> AuthMessage:
        async with db.begin():
            session = await self._repository.find_refresh_session(
                db, hash_opaque_token(body.refresh_token), lock=True
            )
            if session is not None and session.revoked_at is None:
                session.revoked_at = datetime.now(timezone.utc)
        return AuthMessage(message="Signed out")
