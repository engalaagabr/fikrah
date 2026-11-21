"""Application failure codes preserve public HTTP responses at the API boundary."""

import pytest
from fastapi import HTTPException

from app.api.v1 import auth, chat, notes
from app.services.auth_errors import AuthFailure, AuthServiceError
from app.services.chat_errors import ChatFailure, ChatServiceError
from app.services.note_errors import NoteFailure, NoteServiceError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "error_type", "failure", "expected"),
    [
        (auth, AuthServiceError, failure, code)
        for failure, code in [
            (AuthFailure.INVALID_ACCESS_TOKEN, 401),
            (AuthFailure.INVALID_ACTION_TOKEN, 400),
            (AuthFailure.INVALID_CREDENTIALS, 401),
            (AuthFailure.EMAIL_NOT_VERIFIED, 403),
            (AuthFailure.INVALID_GOOGLE_IDENTITY, 401),
            (AuthFailure.GOOGLE_IDENTITY_CONFLICT, 409),
            (AuthFailure.GOOGLE_UNAVAILABLE, 503),
            (AuthFailure.INVALID_REFRESH_TOKEN, 401),
            (AuthFailure.LOGIN_BUDGET_EXCEEDED, 429),
            (AuthFailure.LOGIN_BUDGET_UNAVAILABLE, 503),
            (AuthFailure.PASSWORD_BUSY, 429),
        ]
    ]
    + [
        (notes, NoteServiceError, failure, code)
        for failure, code in [
            (NoteFailure.NOTE_NOT_FOUND, 404),
            (NoteFailure.PROJECT_NOT_FOUND, 404),
            (NoteFailure.IDEMPOTENCY_CONFLICT, 409),
            (NoteFailure.NOTE_DELETED, 410),
            (NoteFailure.EMPTY_CONTENT, 422),
            (NoteFailure.STALE_PROCESSING_RESULT, 409),
            (NoteFailure.PROCESSING_INCOMPLETE, 409),
            (NoteFailure.PROPOSAL_UNAVAILABLE, 409),
        ]
    ]
    + [
        (chat, ChatServiceError, failure, code)
        for failure, code in [
            (ChatFailure.PROJECT_NOT_FOUND, 404),
            (ChatFailure.CONVERSATION_NOT_FOUND, 404),
            (ChatFailure.KNOWLEDGE_UNAVAILABLE, 503),
            (ChatFailure.GENERATION_UNAVAILABLE, 503),
            (ChatFailure.CONVERSATION_CHANGED, 409),
            (ChatFailure.INVALID_MODEL_RESPONSE, 503),
        ]
    ],
)
async def test_api_maps_every_business_failure(module, error_type, failure, expected):
    error = error_type(failure, "Safe failure message")
    assert not hasattr(error, "status_code")
    assert not hasattr(error, "headers")

    async def workflow():
        raise error

    with pytest.raises(HTTPException) as caught:
        await module._execute(workflow())
    assert caught.value.status_code == expected
    assert caught.value.detail == "Safe failure message"
    if failure is AuthFailure.INVALID_CREDENTIALS:
        assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


def test_api_mappings_cover_all_feature_failure_codes():
    assert set(auth.AUTH_FAILURE_STATUSES) == set(AuthFailure)
    assert set(notes.NOTE_FAILURE_STATUSES) == set(NoteFailure)
    assert set(chat.CHAT_FAILURE_STATUSES) == set(ChatFailure)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [AuthFailure.LOGIN_BUDGET_EXCEEDED, AuthFailure.PASSWORD_BUSY]
)
async def test_api_adds_retry_header_from_application_timing(failure):
    async def workflow():
        raise AuthServiceError(failure, "Try later", retry_after=17)

    with pytest.raises(HTTPException) as caught:
        await auth._execute(workflow())
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "17"}
