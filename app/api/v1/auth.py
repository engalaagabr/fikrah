"""HTTP presentation layer for authentication endpoints."""

from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthenticatedUser, AuthServiceDependency, Db
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
from app.schemas.auth import (
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
from app.services.auth_errors import AuthFailure, AuthServiceError

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
Result = TypeVar("Result")

AUTH_FAILURE_STATUSES = {
    AuthFailure.INVALID_ACCESS_TOKEN: 401,
    AuthFailure.INVALID_ACTION_TOKEN: 400,
    AuthFailure.INVALID_CREDENTIALS: 401,
    AuthFailure.EMAIL_NOT_VERIFIED: 403,
    AuthFailure.INVALID_GOOGLE_IDENTITY: 401,
    AuthFailure.GOOGLE_IDENTITY_CONFLICT: 409,
    AuthFailure.GOOGLE_UNAVAILABLE: 503,
    AuthFailure.INVALID_REFRESH_TOKEN: 401,
    AuthFailure.LOGIN_BUDGET_EXCEEDED: 429,
    AuthFailure.LOGIN_BUDGET_UNAVAILABLE: 503,
    AuthFailure.PASSWORD_BUSY: 429,
}


async def _execute(workflow: Awaitable[Result]) -> Result:
    try:
        return await workflow
    except AuthServiceError as error:
        headers = None
        if error.code == AuthFailure.INVALID_CREDENTIALS:
            headers = {"WWW-Authenticate": "Bearer"}
        elif error.retry_after is not None:
            headers = {"Retry-After": str(error.retry_after)}
        raise HTTPException(
            status_code=AUTH_FAILURE_STATUSES[error.code],
            detail=error.message,
            headers=headers,
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
async def register(
    body: Credentials, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(
        service.register(
            EmailPassword(email=str(body.email), password=body.password), db
        )
    )


@router.post("/verify-email", response_model=Message)
async def verify_email(
    body: TokenRequest, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(service.verify_email(ActionToken(token=body.token), db))


@router.post(
    "/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED
)
async def resend_verification(
    body: EmailRequest, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(
        service.resend_verification(EmailAddress(email=str(body.email)), db)
    )


@router.post("/login", response_model=AuthTokens)
async def login(
    body: Credentials, db: Db, service: AuthServiceDependency
) -> AuthTokens:
    return await _tokens(
        service.login(EmailPassword(email=str(body.email), password=body.password), db)
    )


@router.post("/google", response_model=AuthTokens)
async def google_login(
    body: GoogleLoginRequest, db: Db, service: AuthServiceDependency
) -> AuthTokens:
    return await _tokens(
        service.google_login(GoogleIdentityToken(id_token=body.id_token), db)
    )


@router.post(
    "/password-reset/request",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    body: EmailRequest, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(
        service.request_password_reset(EmailAddress(email=str(body.email)), db)
    )


@router.post("/password-reset/confirm", response_model=Message)
async def confirm_password_reset(
    body: ResetPasswordRequest, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(
        service.confirm_password_reset(
            PasswordReset(token=body.token, new_password=body.new_password), db
        )
    )


@router.post("/refresh", response_model=AuthTokens)
async def refresh(
    body: RefreshRequest, db: Db, service: AuthServiceDependency
) -> AuthTokens:
    return await _tokens(
        service.refresh(RefreshToken(refresh_token=body.refresh_token), db)
    )


@router.post("/logout", response_model=Message)
async def logout(
    body: RefreshRequest, db: Db, service: AuthServiceDependency
) -> Message:
    return await _message(
        service.logout(RefreshToken(refresh_token=body.refresh_token), db)
    )


@router.get("/me", response_model=UserView)
async def read_current_user(user: AuthenticatedUser) -> UserView:
    return UserView(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None
    )
