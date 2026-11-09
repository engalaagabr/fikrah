"""HTTP presentation layer for authentication endpoints."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status

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
from app.infrastructure.container import auth_service
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


async def _message(workflow: Awaitable[AuthMessage]) -> Message:
    result = await _execute(workflow)
    return Message(message=result.message)


async def _tokens(workflow: Awaitable[AuthTokenPair]) -> AuthTokens:
    result = await _execute(workflow)
    return AuthTokens(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def register(body: Credentials, db: Db) -> Message:
    return await _message(
        auth_service.register(
            EmailPassword(email=str(body.email), password=body.password), db
        )
    )


@router.post("/verify-email", response_model=Message)
async def verify_email(body: TokenRequest, db: Db) -> Message:
    return await _message(auth_service.verify_email(ActionToken(token=body.token), db))


@router.post(
    "/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED
)
async def resend_verification(body: EmailRequest, db: Db) -> Message:
    return await _message(
        auth_service.resend_verification(EmailAddress(email=str(body.email)), db)
    )


@router.post("/login", response_model=AuthTokens)
async def login(body: Credentials, db: Db) -> AuthTokens:
    return await _tokens(
        auth_service.login(
            EmailPassword(email=str(body.email), password=body.password), db
        )
    )


@router.post("/google", response_model=AuthTokens)
async def google_login(body: GoogleLoginRequest, db: Db) -> AuthTokens:
    return await _tokens(
        auth_service.google_login(GoogleIdentityToken(id_token=body.id_token), db)
    )


@router.post(
    "/password-reset/request",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(body: EmailRequest, db: Db) -> Message:
    return await _message(
        auth_service.request_password_reset(EmailAddress(email=str(body.email)), db)
    )


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(body: ResetPasswordRequest, db: Db) -> Message:
    return await _message(
        auth_service.confirm_password_reset(
            PasswordReset(token=body.token, new_password=body.new_password), db
        )
    )


@router.post("/refresh", response_model=AuthTokens)
async def refresh(body: RefreshRequest, db: Db) -> AuthTokens:
    return await _tokens(
        auth_service.refresh(RefreshToken(refresh_token=body.refresh_token), db)
    )


@router.post("/logout", response_model=Message)
async def logout(body: RefreshRequest, db: Db) -> Message:
    return await _message(
        auth_service.logout(RefreshToken(refresh_token=body.refresh_token), db)
    )


@router.get("/me", response_model=UserView)
async def read_current_user(user: AuthenticatedUser) -> UserView:
    return UserView(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None
    )
