"""Framework-independent data contracts for authentication use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailPassword:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class EmailAddress:
    email: str


@dataclass(frozen=True, slots=True)
class ActionToken:
    token: str


@dataclass(frozen=True, slots=True)
class GoogleIdentityToken:
    id_token: str


@dataclass(frozen=True, slots=True)
class PasswordReset:
    token: str
    new_password: str


@dataclass(frozen=True, slots=True)
class RefreshToken:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class AuthTokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


@dataclass(frozen=True, slots=True)
class AuthMessage:
    message: str
