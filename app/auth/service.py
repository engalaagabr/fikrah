"""Authentication application workflows and account lifecycle use cases."""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import aiosmtplib
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.contracts import (
    ActionToken,
    AuthMessage,
    AuthTokenPair,
    EmailAddress,
    EmailPassword,
    GoogleIdentityToken,
    PasswordReset,
    RefreshToken,
)
from app.auth.errors import AuthServiceError
from app.auth.security import (
    DUMMY_PASSWORD_HASH,
    REFRESH_TOKEN_TTL,
    create_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.infrastructure.email.smtp import send_action_email, send_welcome_email
from app.infrastructure.identity.google import (
    InvalidGoogleToken,
    verify_google_id_token,
)
from app.models import EmailActionToken, EmailSendAttempt, Project, RefreshSession, User


def _auth_error(
    code: int, message: str, *, headers: dict[str, str] | None = None
) -> AuthServiceError:
    return AuthServiceError(code, message, headers=headers)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _send_limit_available(db: AsyncSession, email: str) -> bool:
    now = datetime.now(timezone.utc)
    if db.get_bind().dialect.name == "postgresql":
        # Serialize quota checks per address so concurrent requests cannot exceed
        # the configured per-email cooldown or hourly maximum.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 74192038))"),
            {"email": email},
        )
    recent = await db.scalar(
        select(func.count(EmailSendAttempt.id)).where(
            EmailSendAttempt.email == email,
            EmailSendAttempt.created_at >= now - timedelta(hours=1),
        )
    )
    last = await db.scalar(
        select(EmailSendAttempt.created_at)
        .where(EmailSendAttempt.email == email)
        .order_by(EmailSendAttempt.created_at.desc())
        .limit(1)
    )
    if recent is not None and recent >= 5:
        return False
    if last is not None:
        # SQLite may return naive values in tests; PostgreSQL returns timezone-aware timestamps.
        last = _utc(last)
        if last > now - timedelta(seconds=60):
            return False
    db.add(EmailSendAttempt(email=email))
    await db.flush()
    return True


async def _new_action_token(
    db: AsyncSession, user: User, purpose: str, lifetime: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(EmailActionToken)
        .where(
            EmailActionToken.user_id == user.id,
            EmailActionToken.purpose == purpose,
            EmailActionToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = new_opaque_token()
    db.add(
        EmailActionToken(
            user_id=user.id,
            token_hash=hash_opaque_token(raw),
            purpose=purpose,
            expires_at=now + lifetime,
        )
    )
    await db.flush()
    return raw


async def _issue_session(db: AsyncSession, user: User) -> AuthTokenPair:
    refresh = new_opaque_token()
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_opaque_token(refresh),
            expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
        )
    )
    await db.flush()
    return AuthTokenPair(
        access_token=create_access_token(user.id), refresh_token=refresh
    )


async def register(body: EmailPassword, db: AsyncSession) -> AuthMessage:
    raw_token: str | None = None
    async with db.begin():
        exists = await db.scalar(select(User.id).where(User.email == body.email))
        if exists is None and await _send_limit_available(db, body.email):
            user = User(
                email=body.email,
                password_hash=await asyncio.to_thread(hash_password, body.password),
            )
            db.add(user)
            await db.flush()
            db.add(Project(user_id=user.id, name="General", is_general=True))
            raw_token = await _new_action_token(
                db, user, "verify_email", timedelta(hours=24)
            )
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "verify_email")
            await send_welcome_email(body.email)
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _auth_error(503, "Email delivery is temporarily unavailable") from exc
    return AuthMessage(
        message="If the address can be registered, a verification email will be sent."
    )


async def verify_email(body: ActionToken, db: AsyncSession) -> AuthMessage:
    now = datetime.now(timezone.utc)
    async with db.begin():
        action = await db.scalar(
            select(EmailActionToken)
            .where(
                EmailActionToken.token_hash == hash_opaque_token(body.token),
                EmailActionToken.purpose == "verify_email",
            )
            .with_for_update()
        )
        if (
            action is None
            or action.used_at is not None
            or _utc(action.expires_at) <= now
        ):
            raise _auth_error(400, "The verification link is invalid or expired")
        action.used_at = now
        user = await db.get(User, action.user_id)
        if user is None:
            raise _auth_error(400, "The verification link is invalid or expired")
        user.email_verified_at = now
    return AuthMessage(message="Email verified")


async def resend_verification(body: EmailAddress, db: AsyncSession) -> AuthMessage:
    raw_token: str | None = None
    async with db.begin():
        user = await db.scalar(
            select(User).where(User.email == body.email).with_for_update()
        )
        if (
            user is not None
            and user.email_verified_at is None
            and await _send_limit_available(db, body.email)
        ):
            raw_token = await _new_action_token(
                db, user, "verify_email", timedelta(hours=24)
            )
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "verify_email")
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _auth_error(503, "Email delivery is temporarily unavailable") from exc
    return AuthMessage(
        message="If the address needs verification, an email will be sent."
    )


async def login(body: EmailPassword, db: AsyncSession) -> AuthTokenPair:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        await asyncio.to_thread(verify_password, body.password, DUMMY_PASSWORD_HASH)
        raise _auth_error(
            401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    if not await asyncio.to_thread(verify_password, body.password, user.password_hash):
        raise _auth_error(
            401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    if user.email_verified_at is None:
        raise _auth_error(403, "Verify your email before signing in")
    tokens = await _issue_session(db, user)
    await db.commit()
    return tokens


async def google_login(body: GoogleIdentityToken, db: AsyncSession) -> AuthTokenPair:
    audience = os.getenv("GOOGLE_CLIENT_ID")
    if not audience:
        raise _auth_error(503, "Google sign-in is not configured")
    try:
        claims = await asyncio.to_thread(
            verify_google_id_token, body.id_token, audience
        )
    except InvalidGoogleToken:
        raise _auth_error(401, "Invalid Google ID token")
    email = str(claims.get("email", "")).strip().lower()
    subject = claims.get("sub")
    if not email or not subject or claims.get("email_verified") is not True:
        raise _auth_error(401, "Google account must have a verified email")

    created_user = False
    async with db.begin():
        subject_user = await db.scalar(
            select(User).where(User.google_subject == subject).with_for_update()
        )
        user = await db.scalar(
            select(User).where(User.email == email).with_for_update()
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
            db.add(user)
            await db.flush()
            db.add(Project(user_id=user.id, name="General", is_general=True))
        elif user.google_subject not in (None, subject):
            raise _auth_error(
                409, "This account is linked to a different Google identity"
            )
        else:
            user.google_subject = subject
            user.email_verified_at = user.email_verified_at or datetime.now(
                timezone.utc
            )
        tokens = await _issue_session(db, user)
    if created_user:
        try:
            await send_welcome_email(email)
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _auth_error(503, "Email delivery is temporarily unavailable") from exc
    return tokens


async def request_password_reset(body: EmailAddress, db: AsyncSession) -> AuthMessage:
    raw_token: str | None = None
    async with db.begin():
        user = await db.scalar(
            select(User).where(User.email == body.email).with_for_update()
        )
        if (
            user is not None
            and user.password_hash is not None
            and await _send_limit_available(db, body.email)
        ):
            raw_token = await _new_action_token(
                db, user, "reset_password", timedelta(hours=1)
            )
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "reset_password")
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _auth_error(503, "Email delivery is temporarily unavailable") from exc
    return AuthMessage(
        message="If the account exists, a password reset email will be sent."
    )


async def confirm_password_reset(body: PasswordReset, db: AsyncSession) -> AuthMessage:
    now = datetime.now(timezone.utc)
    async with db.begin():
        action = await db.scalar(
            select(EmailActionToken)
            .where(
                EmailActionToken.token_hash == hash_opaque_token(body.token),
                EmailActionToken.purpose == "reset_password",
            )
            .with_for_update()
        )
        if (
            action is None
            or action.used_at is not None
            or _utc(action.expires_at) <= now
        ):
            raise _auth_error(400, "The password reset link is invalid or expired")
        action.used_at = now
        user = await db.get(User, action.user_id)
        if user is None:
            raise _auth_error(400, "The password reset link is invalid or expired")
        user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )
    return AuthMessage(message="Password reset successfully")


async def refresh(body: RefreshToken, db: AsyncSession) -> AuthTokenPair:
    now = datetime.now(timezone.utc)
    async with db.begin():
        previous = await db.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == hash_opaque_token(body.refresh_token))
            .with_for_update()
        )
        if (
            previous is None
            or previous.revoked_at is not None
            or _utc(previous.expires_at) <= now
        ):
            raise _auth_error(401, "Invalid or expired refresh token")
        user = await db.get(User, previous.user_id)
        if user is None:
            raise _auth_error(401, "Invalid or expired refresh token")
        tokens = await _issue_session(db, user)
        replacement = await db.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_opaque_token(tokens.refresh_token)
            )
        )
        previous.revoked_at = now
        previous.replaced_by_id = replacement.id
    return tokens


async def logout(body: RefreshToken, db: AsyncSession) -> AuthMessage:
    async with db.begin():
        session = await db.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == hash_opaque_token(body.refresh_token))
            .with_for_update()
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
    return AuthMessage(message="Signed out")
