"""Authenticated encryption for tokens awaiting SMTP delivery."""

from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings
from app.core.security import validate_jwt_secret
from app.services.auth_ports import EmailDeliveryError


def _cipher() -> Fernet:
    secret = validate_jwt_secret(get_settings().fikrah_jwt_secret)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"fikrah-email-outbox-v1",
    ).derive(secret.encode())
    return Fernet(urlsafe_b64encode(key))


def protect_email_token(token: str) -> str:
    return _cipher().encrypt(token.encode()).decode()


def reveal_email_token(encrypted: str) -> str:
    try:
        return _cipher().decrypt(encrypted.encode()).decode()
    except (InvalidToken, ValueError, RuntimeError) as error:
        raise EmailDeliveryError from error
