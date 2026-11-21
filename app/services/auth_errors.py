"""Authentication use-case errors independent of the HTTP framework."""

from enum import StrEnum


class AuthFailure(StrEnum):
    INVALID_ACCESS_TOKEN = "invalid_access_token"
    INVALID_ACTION_TOKEN = "invalid_action_token"
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    INVALID_GOOGLE_IDENTITY = "invalid_google_identity"
    GOOGLE_IDENTITY_CONFLICT = "google_identity_conflict"
    GOOGLE_UNAVAILABLE = "google_unavailable"
    INVALID_REFRESH_TOKEN = "invalid_refresh_token"
    LOGIN_BUDGET_EXCEEDED = "login_budget_exceeded"
    LOGIN_BUDGET_UNAVAILABLE = "login_budget_unavailable"
    PASSWORD_BUSY = "password_busy"


class AuthServiceError(Exception):
    """A safe authentication failure that the presentation layer can translate."""

    def __init__(
        self,
        code: AuthFailure,
        message: str,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after
