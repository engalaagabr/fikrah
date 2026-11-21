"""Public upload contract, authorization, budgets and bounded multipart parsing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.body_limits import RequestBodyLimitMiddleware
from app.api.deps import current_user, get_transcription_service
from app.api.v1.transcriptions import router
from app.db.session import get_db_session
from app.infrastructure.container import request_budgets
from app.llm.errors import TranscriptionUnavailableError
from app.services.request_budgets import RequestBudgetExceeded, RequestBudgetUnavailable
from app.services.transcription_service import TranscriptionService


@pytest_asyncio.fixture
async def transcription_api(monkeypatch):
    monkeypatch.setenv("FIKRAH_TRANSCRIPTION_MAX_BYTES", "100")
    db = SimpleNamespace(rollback=AsyncMock())
    provider = SimpleNamespace(
        transcribe=AsyncMock(return_value="فكرة جديدة"), aclose=AsyncMock()
    )
    service = TranscriptionService(lambda: provider, lambda: 100)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(RequestBodyLimitMiddleware, audio_upload_path=router.prefix)

    async def database():
        yield db

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_transcription_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, app, db, provider


@pytest.mark.asyncio
async def test_upload_returns_text_and_releases_database_before_provider(
    transcription_api,
):
    client, app, db, provider = transcription_api

    async def transcribe(audio, mime):
        db.rollback.assert_awaited_once()
        assert audio == b"recording" and mime == "audio/wav"
        return "فكرة جديدة"

    provider.transcribe.side_effect = transcribe
    response = await client.post(
        router.prefix, files={"file": ("voice.wav", b"recording", "audio/wav")}
    )
    assert response.status_code == 200 and response.json() == {"text": "فكرة جديدة"}
    provider.aclose.assert_awaited_once()
    operation = app.openapi()["paths"][router.prefix]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert operation["requestBody"]["content"]["multipart/form-data"]["schema"][
        "required"
    ] == ["file"]


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_upload_requires_authentication(transcription_api, monkeypatch, token):
    client, app, _, provider = transcription_api
    app.dependency_overrides.pop(current_user)
    monkeypatch.setenv(
        "FIKRAH_JWT_SECRET", "transcription-test-secret-at-least-32-characters"
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.post(
        router.prefix,
        headers=headers,
        files={"file": ("voice.wav", b"recording", "audio/wav")},
    )
    assert response.status_code == 401
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "mime", "status"),
    [
        (b"", "audio/wav", 422),
        (b"x" * 101, "audio/wav", 413),
        (b"audio", "image/png", 415),
    ],
)
async def test_invalid_uploads_do_not_call_provider(
    transcription_api, content, mime, status
):
    client, _, _, provider = transcription_api
    response = await client.post(
        router.prefix, files={"file": ("voice", content, mime)}
    )
    assert response.status_code == status
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "files",
    [
        [
            ("file", ("a.wav", b"a", "audio/wav")),
            ("file", ("b.wav", b"b", "audio/wav")),
        ],
        [("wrong-name", ("a.wav", b"a", "audio/wav"))],
    ],
)
async def test_exactly_one_file_field_is_required(transcription_api, files):
    client, _, _, provider = transcription_api
    response = await client.post(router.prefix, files=files)
    assert response.status_code == 422
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_extra_form_fields_are_rejected(transcription_api):
    client, _, _, provider = transcription_api
    response = await client.post(
        router.prefix,
        files={"file": ("voice.wav", b"audio", "audio/wav")},
        data={"user_id": str(uuid4())},
    )
    assert response.status_code == 422
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_json_upload_is_rejected(transcription_api):
    client, _, _, provider = transcription_api
    response = await client.post(router.prefix, json={"file": "not audio"})
    assert response.status_code == 415
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [(RequestBudgetExceeded(30), 429), (RequestBudgetUnavailable(), 503)],
)
async def test_upload_uses_existing_llm_request_budget(
    transcription_api, monkeypatch, error, status
):
    client, _, _, provider = transcription_api
    monkeypatch.setattr(request_budgets, "llm", AsyncMock(side_effect=error))
    response = await client.post(
        router.prefix, files={"file": ("voice.wav", b"audio", "audio/wav")}
    )
    assert response.status_code == status
    if status == 429:
        assert response.headers["Retry-After"] == "30"
    provider.transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_has_a_safe_public_response(transcription_api):
    client, _, _, provider = transcription_api
    provider.transcribe.side_effect = TranscriptionUnavailableError(
        "private token and audio"
    )
    response = await client.post(
        router.prefix, files={"file": ("voice.wav", b"audio", "audio/wav")}
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Audio transcription is temporarily unavailable"
    }
    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "allowed"),
    [
        ("/v1/transcriptions", "POST", True),
        ("/v1/transcriptions/", "POST", True),
        ("/v1/transcriptions/other", "POST", False),
        ("/v1/transcriptions", "GET", False),
        ("/v1/projects", "POST", False),
    ],
)
async def test_upload_allowance_does_not_weaken_other_routes(
    monkeypatch, path, method, allowed
):
    monkeypatch.setenv("FIKRAH_REQUEST_MAX_BYTES", "10")
    monkeypatch.setenv("FIKRAH_TRANSCRIPTION_MAX_BYTES", "100")
    reached, sent = [], []

    async def downstream(*_):
        reached.append(True)

    async def receive():
        return {"type": "http.request", "body": b"x" * 20, "more_body": False}

    async def send(message):
        sent.append(message)

    await RequestBodyLimitMiddleware(downstream, audio_upload_path=router.prefix)(
        {"type": "http", "path": path, "method": method, "headers": []}, receive, send
    )
    assert bool(reached) is allowed
    if not allowed:
        assert sent[0]["status"] == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [True, False])
async def test_multipart_body_is_bounded_before_parsing(monkeypatch, declared):
    monkeypatch.setenv("FIKRAH_TRANSCRIPTION_MAX_BYTES", "100")
    sent, reached = [], []

    async def downstream(*_):
        reached.append(True)

    async def receive():
        return {"type": "http.request", "body": b"x" * 65_637, "more_body": False}

    async def send(message):
        sent.append(message)

    await RequestBodyLimitMiddleware(downstream, audio_upload_path=router.prefix)(
        {
            "type": "http",
            "path": router.prefix,
            "method": "POST",
            "headers": [(b"content-length", b"65637")] if declared else [],
        },
        receive,
        send,
    )
    assert reached == [] and sent[0]["status"] == 413
