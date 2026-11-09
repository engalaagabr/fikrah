"""Versioned authentication API for mobile clients."""

from datetime import datetime, timedelta, timezone
import os
from typing import Annotated
from uuid import UUID

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import send_action_email, send_welcome_email
from app.auth.security import (
    REFRESH_TOKEN_TTL,
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.database import get_db_session
from app.models import EmailActionToken, EmailSendAttempt, Project, RefreshSession, User

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)
Db = Annotated[AsyncSession, Depends(get_db_session)]


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=15, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class EmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ResetPasswordRequest(TokenRequest):
    new_password: str = Field(min_length=15, max_length=128)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class Message(BaseModel):
    message: str


class UserView(BaseModel):
    id: UUID
    email: EmailStr
    email_verified: bool


def _http_error(code: int, message: str, *, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status_code=code, detail=message, headers=headers)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _send_limit_available(db: AsyncSession, email: str) -> bool:
    now = datetime.now(timezone.utc)
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
    db.add(EmailActionToken(
        user_id=user.id,
        token_hash=hash_opaque_token(raw),
        purpose=purpose,
        expires_at=now + lifetime,
    ))
    await db.flush()
    return raw


async def _issue_session(db: AsyncSession, user: User) -> AuthTokens:
    refresh = new_opaque_token()
    db.add(RefreshSession(
        user_id=user.id,
        token_hash=hash_opaque_token(refresh),
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
    ))
    await db.flush()
    return AuthTokens(access_token=create_access_token(user.id), refresh_token=refresh)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Db,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _http_error(401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = decode_access_token(credentials.credentials)
    except (InvalidTokenError, ValueError, KeyError):
        raise _http_error(401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    user = await db.get(User, user_id)
    if user is None:
        raise _http_error(401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    return user


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def register(body: Credentials, db: Db) -> Message:
    raw_token: str | None = None
    async with db.begin():
        exists = await db.scalar(select(User.id).where(User.email == body.email))
        if exists is None and await _send_limit_available(db, body.email):
            user = User(email=body.email, password_hash=await run_in_threadpool(hash_password, body.password))
            db.add(user)
            await db.flush()
            db.add(Project(user_id=user.id, name="General", is_general=True))
            raw_token = await _new_action_token(db, user, "verify_email", timedelta(hours=24))
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "verify_email")
            await send_welcome_email(body.email)
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _http_error(503, "Email delivery is temporarily unavailable") from exc
    return Message(message="If the address can be registered, a verification email will be sent.")


@router.post("/verify-email", response_model=Message)
async def verify_email(body: TokenRequest, db: Db) -> Message:
    now = datetime.now(timezone.utc)
    async with db.begin():
        action = await db.scalar(
            select(EmailActionToken).where(
                EmailActionToken.token_hash == hash_opaque_token(body.token),
                EmailActionToken.purpose == "verify_email",
            ).with_for_update()
        )
        if action is None or action.used_at is not None or _utc(action.expires_at) <= now:
            raise _http_error(400, "The verification link is invalid or expired")
        action.used_at = now
        user = await db.get(User, action.user_id)
        if user is None:
            raise _http_error(400, "The verification link is invalid or expired")
        user.email_verified_at = now
    return Message(message="Email verified")


@router.post("/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(body: EmailRequest, db: Db) -> Message:
    raw_token: str | None = None
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == body.email).with_for_update())
        if user is not None and user.email_verified_at is None and await _send_limit_available(db, body.email):
            raw_token = await _new_action_token(db, user, "verify_email", timedelta(hours=24))
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "verify_email")
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _http_error(503, "Email delivery is temporarily unavailable") from exc
    return Message(message="If the address needs verification, an email will be sent.")


@router.post("/login", response_model=AuthTokens)
async def login(body: Credentials, db: Db) -> AuthTokens:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or user.password_hash is None:
        await run_in_threadpool(verify_password, body.password, DUMMY_PASSWORD_HASH)
        raise _http_error(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    if not await run_in_threadpool(verify_password, body.password, user.password_hash):
        raise _http_error(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    if user.email_verified_at is None:
        raise _http_error(403, "Verify your email before signing in")
    tokens = await _issue_session(db, user)
    await db.commit()
    return tokens


@router.post("/google", response_model=AuthTokens)
async def google_login(body: GoogleLoginRequest, db: Db) -> AuthTokens:
    audience = os.getenv("GOOGLE_CLIENT_ID")
    if not audience:
        raise _http_error(503, "Google sign-in is not configured")
    try:
        claims = await run_in_threadpool(
            id_token.verify_oauth2_token, body.id_token, GoogleRequest(), audience
        )
    except (ValueError, GoogleAuthError):
        raise _http_error(401, "Invalid Google ID token")
    email = str(claims.get("email", "")).strip().lower()
    subject = claims.get("sub")
    if not email or not subject or claims.get("email_verified") is not True:
        raise _http_error(401, "Google account must have a verified email")

    created_user = False
    async with db.begin():
        subject_user = await db.scalar(
            select(User).where(User.google_subject == subject).with_for_update()
        )
        user = await db.scalar(select(User).where(User.email == email).with_for_update())
        if subject_user is not None and subject_user.email != email:
            raise _http_error(409, "The Google identity is linked to a different email address")
        if user is None:
            created_user = True
            user = User(email=email, google_subject=subject, email_verified_at=datetime.now(timezone.utc))
            db.add(user)
            await db.flush()
            db.add(Project(user_id=user.id, name="General", is_general=True))
        elif user.google_subject not in (None, subject):
            raise _http_error(409, "This account is linked to a different Google identity")
        else:
            user.google_subject = subject
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        tokens = await _issue_session(db, user)
    if created_user:
        try:
            await send_welcome_email(email)
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _http_error(503, "Email delivery is temporarily unavailable") from exc
    return tokens


@router.post("/password-reset/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: EmailRequest, db: Db) -> Message:
    raw_token: str | None = None
    async with db.begin():
        user = await db.scalar(select(User).where(User.email == body.email).with_for_update())
        if user is not None and user.password_hash is not None and await _send_limit_available(db, body.email):
            raw_token = await _new_action_token(db, user, "reset_password", timedelta(hours=1))
    if raw_token is not None:
        try:
            await send_action_email(body.email, raw_token, "reset_password")
        except (RuntimeError, OSError, aiosmtplib.SMTPException) as exc:
            raise _http_error(503, "Email delivery is temporarily unavailable") from exc
    return Message(message="If the account exists, a password reset email will be sent.")


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(body: ResetPasswordRequest, db: Db) -> Message:
    now = datetime.now(timezone.utc)
    async with db.begin():
        action = await db.scalar(
            select(EmailActionToken).where(
                EmailActionToken.token_hash == hash_opaque_token(body.token),
                EmailActionToken.purpose == "reset_password",
            ).with_for_update()
        )
        if action is None or action.used_at is not None or _utc(action.expires_at) <= now:
            raise _http_error(400, "The password reset link is invalid or expired")
        action.used_at = now
        user = await db.get(User, action.user_id)
        if user is None:
            raise _http_error(400, "The password reset link is invalid or expired")
        user.password_hash = await run_in_threadpool(hash_password, body.new_password)
        await db.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    return Message(message="Password reset successfully")


@router.post("/refresh", response_model=AuthTokens)
async def refresh(body: RefreshRequest, db: Db) -> AuthTokens:
    now = datetime.now(timezone.utc)
    async with db.begin():
        previous = await db.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_opaque_token(body.refresh_token)
            ).with_for_update()
        )
        if previous is None or previous.revoked_at is not None or _utc(previous.expires_at) <= now:
            raise _http_error(401, "Invalid or expired refresh token")
        user = await db.get(User, previous.user_id)
        if user is None:
            raise _http_error(401, "Invalid or expired refresh token")
        tokens = await _issue_session(db, user)
        replacement = await db.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_opaque_token(tokens.refresh_token))
        )
        previous.revoked_at = now
        previous.replaced_by_id = replacement.id
    return tokens


@router.post("/logout", response_model=Message)
async def logout(body: RefreshRequest, db: Db) -> Message:
    async with db.begin():
        session = await db.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_opaque_token(body.refresh_token)
            ).with_for_update()
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
    return Message(message="Signed out")


@router.get("/me", response_model=UserView)
async def read_current_user(user: Annotated[User, Depends(current_user)]) -> UserView:
    return UserView(id=user.id, email=user.email, email_verified=user.email_verified_at is not None)
