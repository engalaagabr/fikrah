from uuid import uuid4

import jwt
import pytest

from app.core.security import (
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

    family_id = uuid4()
    token = create_access_token(user_id, family_id)

    assert decode_access_token(token).user_id == user_id
    assert decode_access_token(token).family_id == family_id


def test_access_token_rejects_other_token_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIKRAH_JWT_SECRET", "x" * 48)
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(uuid4()), "sid": str(uuid4()), "type": "refresh", "iat": now,
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


@pytest.mark.parametrize(
    "secret",
    ["", "too-short", "replace-with-a-random-secret-at-least-32-characters"],
)
def test_auth_rejects_missing_short_and_public_example_secrets(monkeypatch, secret):
    from app.core.security import validate_jwt_secret

    monkeypatch.setenv("FIKRAH_JWT_SECRET", secret)
    with pytest.raises(RuntimeError, match="FIKRAH_JWT_SECRET"):
        validate_jwt_secret(secret)
    with pytest.raises(RuntimeError, match="FIKRAH_JWT_SECRET"):
        create_access_token(uuid4(), uuid4())
