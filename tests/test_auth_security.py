from uuid import uuid4

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)


def test_password_hash_verifies_without_storing_plaintext() -> None:
    password = "a long passphrase with enough length"
    encoded = hash_password(password)

    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("a different passphrase", encoded)


def test_access_token_contains_user_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "x" * 48)
    user_id = uuid4()

    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_access_token_rejects_other_token_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "x" * 48)
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(uuid4()), "type": "refresh", "iat": now,
         "exp": now + timedelta(minutes=1), "iss": "fikrah-api"},
        "x" * 48,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_opaque_token_hash_is_deterministic_and_one_way() -> None:
    token = "random-high-entropy-token"

    assert hash_opaque_token(token) == hash_opaque_token(token)
    assert hash_opaque_token(token) != token
