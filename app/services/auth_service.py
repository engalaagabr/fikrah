"""Authentication application workflows and account lifecycle use cases."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.auth import (
    ActionToken,
    AuthMessage,
    AuthTokenPair,
    EmailAddress,
    EmailPassword,
    GoogleIdentityToken,
    PasswordReset,
    RefreshToken,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    REFRESH_TOKEN_TTL,
    AccessIdentity,
    PasswordWorkBusy,
    create_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    run_password_work,
    verify_password,
)
from app.models import EmailActionToken, EmailDelivery, Project, RefreshSession, User
from app.repositories.auth import AuthRepository
from app.repositories.email import EmailOutboxRepository
from app.services.auth_errors import AuthFailure, AuthServiceError
from app.services.auth_ports import GoogleIdentityTokenError
from app.services.email_delivery_service import EmailDeliveryService
from app.services.request_budgets import RequestBudgetExceeded, RequestBudgetUnavailable

logger = logging.getLogger(__name__)

SendActionEmail = Callable[[str, str, str], Awaitable[None]]
SendWelcomeEmail = Callable[[str], Awaitable[None]]
VerifyGoogleIdToken = Callable[[str, str], dict[str, object]]
GoogleClientId = Callable[[], str | None]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _password_work(operation: Callable, *args):
    try:
        return await run_password_work(operation, *args)
    except PasswordWorkBusy as error:
        raise AuthServiceError(
            AuthFailure.PASSWORD_BUSY, "Password processing is busy", retry_after=1
        ) from error


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
        ),
    )
    return raw


async def _issue_session(
    db: AsyncSession,
    user: User,
    repository: AuthRepository,
    family_id: UUID | None = None,
) -> AuthTokenPair:
    refresh = new_opaque_token()
    session = RefreshSession(
        user_id=user.id,
        token_hash=hash_opaque_token(refresh),
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
    )
    if family_id is not None:
        session.family_id = family_id
    await repository.add_refresh_session(db, session)
    return AuthTokenPair(
        access_token=create_access_token(user.id, session.family_id),
        refresh_token=refresh,
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
        protect_email_token: Callable[[str], str],
        reveal_email_token: Callable[[str], str],
        repository: AuthRepository | None = None,
        login_budget: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.send_action_email = send_action_email
        self.send_welcome_email = send_welcome_email
        self.verify_google_id_token = verify_google_id_token
        self.google_client_id = google_client_id
        self._protect_email_token = protect_email_token
        self._reveal_email_token = reveal_email_token
        self._email_repository = EmailOutboxRepository()
        self._repository = repository or AuthRepository()
        self._login_budget = login_budget

    async def _queue_email(
        self, db: AsyncSession, user: User, purpose: str, token: str | None = None
    ) -> UUID:
        delivery = EmailDelivery(
            user_id=user.id,
            recipient=user.email,
            purpose=purpose,
            token_hash=hash_opaque_token(token) if token is not None else None,
            encrypted_token=self._protect_email_token(token)
            if token is not None
            else None,
        )
        await self._email_repository.add(db, delivery)
        return delivery.id

    async def _deliver_emails(self, db: AsyncSession, delivery_ids: list[UUID]) -> None:
        sender = EmailDeliveryService(
            self.send_action_email,
            self.send_welcome_email,
            self._reveal_email_token,
            self._email_repository,
        )
        for delivery_id in delivery_ids:
            try:
                await sender.deliver(db, delivery_id)
            except SQLAlchemyError:
                await db.rollback()
                logger.warning(
                    "Email dispatch deferred after database error: delivery=%s",
                    delivery_id,
                )

    async def authenticated_user(
        self, db: AsyncSession, identity: AccessIdentity
    ) -> User:
        user = await self._repository.active_session_user(
            db, identity.user_id, identity.family_id, datetime.now(timezone.utc)
        )
        if user is None:
            raise AuthServiceError(
                AuthFailure.INVALID_ACCESS_TOKEN, "Invalid or expired access token"
            )
        return user

    async def _locked_action_user(
        self, db: AsyncSession, token: str, purpose: str
    ) -> tuple[EmailActionToken, User]:
        token_hash = hash_opaque_token(token)
        initial = await self._repository.find_action_token(
            db, token_hash, purpose, lock=False
        )
        message = (
            "The verification link is invalid or expired"
            if purpose == "verify_email"
            else "The password reset link is invalid or expired"
        )
        if initial is None:
            raise AuthServiceError(AuthFailure.INVALID_ACTION_TOKEN, message)
        user = await self._repository.get_user(db, initial.user_id, lock=True)
        action = await self._repository.find_action_token(db, token_hash, purpose)
        now = datetime.now(timezone.utc)
        if (
            user is None
            or action is None
            or action.used_at is not None
            or _utc(action.expires_at) <= now
        ):
            raise AuthServiceError(AuthFailure.INVALID_ACTION_TOKEN, message)
        return action, user

    async def register(self, body: EmailPassword, db: AsyncSession) -> AuthMessage:
        delivery_ids: list[UUID] = []
        async with db.begin():
            await self._repository.lock_account_creation(db, body.email)
            existing_user_id = await self._repository.find_user_id_by_email(
                db, body.email
            )
            if existing_user_id is None and await _send_limit_available(
                db, body.email, self._repository
            ):
                user = User(
                    email=body.email,
                    password_hash=await _password_work(hash_password, body.password),
                )
                await self._repository.add_user(db, user)
                self._repository.add_project(
                    db, Project(user_id=user.id, name="General", is_general=True)
                )
                raw_token = await _new_action_token(
                    db, user, "verify_email", timedelta(hours=24), self._repository
                )
                delivery_ids.append(
                    await self._queue_email(db, user, "verify_email", raw_token)
                )
                delivery_ids.append(await self._queue_email(db, user, "welcome"))
        await self._deliver_emails(db, delivery_ids)
        return AuthMessage(
            message="If the address can be registered, a verification email will be sent."
        )

    async def verify_email(self, body: ActionToken, db: AsyncSession) -> AuthMessage:
        now = datetime.now(timezone.utc)
        async with db.begin():
            action, user = await self._locked_action_user(
                db, body.token, "verify_email"
            )
            action.used_at = now
            user.email_verified_at = now
        return AuthMessage(message="Email verified")

    async def resend_verification(
        self, body: EmailAddress, db: AsyncSession
    ) -> AuthMessage:
        delivery_ids: list[UUID] = []
        async with db.begin():
            user = await self._repository.find_user_by_email(db, body.email, lock=True)
            if (
                user is not None
                and user.email_verified_at is None
                and await _send_limit_available(db, body.email, self._repository)
            ):
                raw_token = await _new_action_token(
                    db, user, "verify_email", timedelta(hours=24), self._repository
                )
                delivery_ids.append(
                    await self._queue_email(db, user, "verify_email", raw_token)
                )
        await self._deliver_emails(db, delivery_ids)
        return AuthMessage(
            message="If the address needs verification, an email will be sent."
        )

    async def login(self, body: EmailPassword, db: AsyncSession) -> AuthTokenPair:
        if self._login_budget is not None:
            try:
                await self._login_budget(body.email)
            except RequestBudgetExceeded as error:
                raise AuthServiceError(
                    AuthFailure.LOGIN_BUDGET_EXCEEDED,
                    "Too many login attempts",
                    retry_after=error.retry_after,
                ) from error
            except RequestBudgetUnavailable as error:
                raise AuthServiceError(
                    AuthFailure.LOGIN_BUDGET_UNAVAILABLE,
                    "Authentication is temporarily unavailable",
                ) from error
        user = await self._repository.find_user_by_email(db, body.email, lock=True)
        if user is None or user.password_hash is None:
            await _password_work(verify_password, body.password, DUMMY_PASSWORD_HASH)
            raise AuthServiceError(
                AuthFailure.INVALID_CREDENTIALS, "Invalid email or password"
            )
        if not await _password_work(verify_password, body.password, user.password_hash):
            raise AuthServiceError(
                AuthFailure.INVALID_CREDENTIALS, "Invalid email or password"
            )
        if user.email_verified_at is None:
            raise AuthServiceError(
                AuthFailure.EMAIL_NOT_VERIFIED, "Verify your email before signing in"
            )
        tokens = await _issue_session(db, user, self._repository)
        await db.commit()
        return tokens

    async def google_login(
        self, body: GoogleIdentityToken, db: AsyncSession
    ) -> AuthTokenPair:
        audience = self.google_client_id()
        if not audience:
            raise AuthServiceError(
                AuthFailure.GOOGLE_UNAVAILABLE, "Google sign-in is not configured"
            )
        try:
            claims = await asyncio.to_thread(
                self.verify_google_id_token, body.id_token, audience
            )
        except GoogleIdentityTokenError:
            raise AuthServiceError(
                AuthFailure.INVALID_GOOGLE_IDENTITY, "Invalid Google ID token"
            )
        email = str(claims.get("email", "")).strip().lower()
        subject = claims.get("sub")
        if not email or not subject or claims.get("email_verified") is not True:
            raise AuthServiceError(
                AuthFailure.INVALID_GOOGLE_IDENTITY,
                "Google account must have a verified email",
            )

        delivery_ids: list[UUID] = []
        async with db.begin():
            await self._repository.lock_account_creation(db, email, str(subject))
            subject_user = await self._repository.find_user_by_google_subject(
                db, subject
            )
            authoritative_email = email.endswith("@gmail.com") or (
                isinstance(claims.get("hd"), str) and bool(claims["hd"].strip())
            )
            if subject_user is None and not authoritative_email:
                raise AuthServiceError(
                    AuthFailure.INVALID_GOOGLE_IDENTITY,
                    "Google cannot establish current ownership of this email address",
                )
            user = await self._repository.find_user_by_email(db, email, lock=True)
            if subject_user is not None and subject_user.email != email:
                raise AuthServiceError(
                    AuthFailure.GOOGLE_IDENTITY_CONFLICT,
                    "The Google identity is linked to a different email address",
                )
            if user is None:
                user = User(
                    email=email,
                    google_subject=subject,
                    email_verified_at=datetime.now(timezone.utc),
                )
                await self._repository.add_user(db, user)
                self._repository.add_project(
                    db, Project(user_id=user.id, name="General", is_general=True)
                )
                delivery_ids.append(await self._queue_email(db, user, "welcome"))
            elif user.google_subject not in (None, subject):
                raise AuthServiceError(
                    AuthFailure.GOOGLE_IDENTITY_CONFLICT,
                    "This account is linked to a different Google identity",
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
        await self._deliver_emails(db, delivery_ids)
        return tokens

    async def request_password_reset(
        self, body: EmailAddress, db: AsyncSession
    ) -> AuthMessage:
        delivery_ids: list[UUID] = []
        async with db.begin():
            user = await self._repository.find_user_by_email(db, body.email, lock=True)
            if (
                user is not None
                and user.password_hash is not None
                and await _send_limit_available(db, body.email, self._repository)
            ):
                raw_token = await _new_action_token(
                    db, user, "reset_password", timedelta(hours=1), self._repository
                )
                delivery_ids.append(
                    await self._queue_email(db, user, "reset_password", raw_token)
                )
        await self._deliver_emails(db, delivery_ids)
        return AuthMessage(
            message="If the account exists, a password reset email will be sent."
        )

    async def confirm_password_reset(
        self, body: PasswordReset, db: AsyncSession
    ) -> AuthMessage:
        now = datetime.now(timezone.utc)
        async with db.begin():
            action, user = await self._locked_action_user(
                db, body.token, "reset_password"
            )
            action.used_at = now
            user.password_hash = await _password_work(hash_password, body.new_password)
            await self._repository.revoke_active_refresh_sessions(db, user.id, now)
        return AuthMessage(message="Password reset successfully")

    async def refresh(self, body: RefreshToken, db: AsyncSession) -> AuthTokenPair:
        now = datetime.now(timezone.utc)
        tokens: AuthTokenPair | None = None
        async with db.begin():
            initial = await self._repository.find_refresh_session(
                db, hash_opaque_token(body.refresh_token)
            )
            if initial is not None:
                user = await self._repository.get_user(db, initial.user_id, lock=True)
                previous = await self._repository.find_refresh_session(
                    db, hash_opaque_token(body.refresh_token), lock=True
                )
                if user is not None and previous is not None:
                    if previous.revoked_at is not None:
                        # Commit containment before raising; an exception inside
                        # db.begin() would roll this revocation back.
                        await self._repository.revoke_refresh_family(
                            db, user.id, previous.family_id, now
                        )
                    elif (
                        _utc(previous.expires_at) > now
                        and user.email_verified_at is not None
                    ):
                        tokens = await _issue_session(
                            db, user, self._repository, previous.family_id
                        )
                        replacement = await self._repository.find_refresh_session(
                            db, hash_opaque_token(tokens.refresh_token)
                        )
                        previous.revoked_at = now
                        previous.replaced_by_id = replacement.id
        if tokens is None:
            raise AuthServiceError(
                AuthFailure.INVALID_REFRESH_TOKEN, "Invalid or expired refresh token"
            )
        return tokens

    async def logout(self, body: RefreshToken, db: AsyncSession) -> AuthMessage:
        async with db.begin():
            session = await self._repository.find_refresh_session(
                db, hash_opaque_token(body.refresh_token)
            )
            if session is not None:
                user = await self._repository.get_user(db, session.user_id, lock=True)
                if user is not None:
                    await self._repository.revoke_refresh_family(
                        db, user.id, session.family_id, datetime.now(timezone.utc)
                    )
        return AuthMessage(message="Signed out")
