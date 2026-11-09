"""HTTP presentation layer for authentication endpoints."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import service
from app.auth.dependencies import Db, current_user
from app.auth.errors import AuthServiceError
from app.auth.schemas import (
    AuthTokens,
    Credentials,
    EmailRequest,
    GoogleLoginRequest,
    Message,
    RefreshRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserView,
)
from app.models import User

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
AuthenticatedUser = Annotated[User, Depends(current_user)]
Result = TypeVar("Result")


async def _execute(workflow: Awaitable[Result]) -> Result:
    try:
        return await workflow
    except AuthServiceError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.message,
            headers=error.headers,
        ) from error


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def register(body: Credentials, db: Db) -> Message:
    return await _execute(service.register(body, db))


@router.post("/verify-email", response_model=Message)
async def verify_email(body: TokenRequest, db: Db) -> Message:
    return await _execute(service.verify_email(body, db))


@router.post(
    "/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED
)
async def resend_verification(body: EmailRequest, db: Db) -> Message:
    return await _execute(service.resend_verification(body, db))


@router.post("/login", response_model=AuthTokens)
async def login(body: Credentials, db: Db) -> AuthTokens:
    return await _execute(service.login(body, db))


@router.post("/google", response_model=AuthTokens)
async def google_login(body: GoogleLoginRequest, db: Db) -> AuthTokens:
    return await _execute(service.google_login(body, db))


@router.post(
    "/password-reset/request",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(body: EmailRequest, db: Db) -> Message:
    return await _execute(service.request_password_reset(body, db))


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(body: ResetPasswordRequest, db: Db) -> Message:
    return await _execute(service.confirm_password_reset(body, db))


@router.post("/refresh", response_model=AuthTokens)
async def refresh(body: RefreshRequest, db: Db) -> AuthTokens:
    return await _execute(service.refresh(body, db))


@router.post("/logout", response_model=Message)
async def logout(body: RefreshRequest, db: Db) -> Message:
    return await _execute(service.logout(body, db))


@router.get("/me", response_model=UserView)
async def read_current_user(user: AuthenticatedUser) -> UserView:
    return UserView(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None
    )
