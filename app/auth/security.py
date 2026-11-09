"""Password, email-token, and access-token helpers."""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from uuid import UUID

import jwt
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("FIKRAH non-user password timing value")
JWT_ISSUER = "fikrah-api"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hasher.verify(password, encoded_hash)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(user_id: UUID) -> str:
    secret = os.getenv("FIKRAH_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("FIKRAH_JWT_SECRET must contain at least 32 characters")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "type": "access", "iat": now,
         "exp": now + ACCESS_TOKEN_TTL, "iss": JWT_ISSUER},
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> UUID:
    secret = os.getenv("FIKRAH_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("FIKRAH_JWT_SECRET must contain at least 32 characters")
    payload = jwt.decode(token, secret, algorithms=["HS256"], issuer=JWT_ISSUER)
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return UUID(payload["sub"])
