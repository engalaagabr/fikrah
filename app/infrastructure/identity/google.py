"""Google identity token verification adapter."""

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.auth.ports import GoogleIdentityTokenError


def verify_google_id_token(token: str, audience: str) -> dict[str, object]:
    try:
        return id_token.verify_oauth2_token(token, Request(), audience)
    except (ValueError, GoogleAuthError) as error:
        raise GoogleIdentityTokenError from error
