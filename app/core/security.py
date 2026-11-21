"""Password, email-token, and access-token helpers."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("FIKRAH non-user password timing value")
JWT_ISSUER = "fikrah-api"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
_PUBLIC_JWT_PLACEHOLDERS = {
    "replace-with-a-random-secret-at-least-32-characters",
}


def validate_jwt_secret(secret: str) -> str:
    if len(secret) < 32:
        raise RuntimeError("FIKRAH_JWT_SECRET must contain at least 32 characters")
    if secret.strip().lower() in _PUBLIC_JWT_PLACEHOLDERS:
        raise RuntimeError("FIKRAH_JWT_SECRET must not use a public example value")
    return secret


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hasher.verify(password, encoded_hash)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class AccessIdentity:
    user_id: UUID
    family_id: UUID


def create_access_token(user_id: UUID, family_id: UUID) -> str:
    secret = validate_jwt_secret(get_settings().fikrah_jwt_secret)
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(family_id),
            "type": "access",
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
            "iss": JWT_ISSUER,
        },
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> AccessIdentity:
    secret = validate_jwt_secret(get_settings().fikrah_jwt_secret)
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=JWT_ISSUER,
        options={"require": ["sub", "sid", "type", "iat", "exp", "iss"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return AccessIdentity(UUID(payload["sub"]), UUID(payload["sid"]))
