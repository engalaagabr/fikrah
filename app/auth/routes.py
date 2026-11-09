"""HTTP presentation layer for authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth import service
from app.auth.dependencies import Db, current_user
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


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def register(body: Credentials, db: Db) -> Message:
    return await service.register(body, db)


@router.post("/verify-email", response_model=Message)
async def verify_email(body: TokenRequest, db: Db) -> Message:
    return await service.verify_email(body, db)


@router.post(
    "/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED
)
async def resend_verification(body: EmailRequest, db: Db) -> Message:
    return await service.resend_verification(body, db)


@router.post("/login", response_model=AuthTokens)
async def login(body: Credentials, db: Db) -> AuthTokens:
    return await service.login(body, db)


@router.post("/google", response_model=AuthTokens)
async def google_login(body: GoogleLoginRequest, db: Db) -> AuthTokens:
    return await service.google_login(body, db)


@router.post(
    "/password-reset/request",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(body: EmailRequest, db: Db) -> Message:
    return await service.request_password_reset(body, db)


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(body: ResetPasswordRequest, db: Db) -> Message:
    return await service.confirm_password_reset(body, db)


@router.post("/refresh", response_model=AuthTokens)
async def refresh(body: RefreshRequest, db: Db) -> AuthTokens:
    return await service.refresh(body, db)


@router.post("/logout", response_model=Message)
async def logout(body: RefreshRequest, db: Db) -> Message:
    return await service.logout(body, db)


@router.get("/me", response_model=UserView)
async def read_current_user(user: AuthenticatedUser) -> UserView:
    return UserView(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None
    )
