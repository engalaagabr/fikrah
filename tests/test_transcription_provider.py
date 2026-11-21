"""Recorded audio boundaries and Gemini transport without paid provider calls."""

import base64
import json
from unittest.mock import Mock

import httpx
import pytest

from app.llm.errors import AudioRejectedError, TranscriptionUnavailableError
from app.llm.factory import LLMProviderFactory
from app.llm.providers.gemini_transcription import GeminiAudioTranscriber

_AsyncClient = httpx.AsyncClient


def make_adapter(monkeypatch, handler, mode="verbatim"):
    monkeypatch.setattr(
        "app.llm.providers.gemini_transcription.httpx.AsyncClient",
        lambda **kw: _AsyncClient(transport=httpx.MockTransport(handler), **kw),
    )
    return GeminiAudioTranscriber(
        "private-test-key", "gemini-3.5-transcribe", mode=mode
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["verbatim", "smart"])
async def test_provider_uses_inline_audio_and_does_not_store_interactions(
    monkeypatch, mode
):
    def handle(request):
        assert (
            str(request.url)
            == "https://generativelanguage.googleapis.com/v1beta/interactions"
        )
        assert request.headers["x-goog-api-key"] == "private-test-key"
        assert request.headers["Api-Revision"] == "2026-05-20"
        data = json.loads(request.content)
        assert data == {
            "model": "gemini-3.5-transcribe",
            "store": False,
            "input": [
                {
                    "type": "audio",
                    "data": base64.b64encode(b"audio").decode(),
                    "mime_type": "audio/wav",
                }
            ],
            "generation_config": {"transcription_config": {"mode": {"type": mode}}},
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "text", "text": "فكرة "},
                            {"type": "text", "text": "جديدة"},
                        ],
                    }
                ],
            },
        )

    adapter = make_adapter(monkeypatch, handle, mode)
    try:
        assert await adapter.transcribe(b"audio", "audio/wav") == "فكرة جديدة"
    finally:
        await adapter.aclose()
    assert adapter._client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 422, 401, 403, 404, 429, 500, 503, 307])
async def test_provider_maps_errors_without_leaking_upstream_body(monkeypatch, status):
    adapter = make_adapter(
        monkeypatch, lambda _: httpx.Response(status, text="private upstream details")
    )
    expected = (
        AudioRejectedError if status in {400, 422} else TranscriptionUnavailableError
    )
    try:
        with pytest.raises(expected) as caught:
            await adapter.transcribe(b"audio", "audio/wav")
        assert "private" not in str(caught.value)
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"status": "incomplete", "steps": []},
        {"status": "completed", "steps": None},
        {"status": "completed", "steps": []},
        {
            "status": "completed",
            "steps": [
                {"type": "model_output", "content": [{"type": "text", "text": 42}]}
            ],
        },
    ],
)
async def test_provider_rejects_malformed_or_incomplete_transcripts(
    monkeypatch, payload
):
    adapter = make_adapter(monkeypatch, lambda _: httpx.Response(200, json=payload))
    try:
        with pytest.raises(TranscriptionUnavailableError):
            await adapter.transcribe(b"audio", "audio/wav")
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["invalid-json", "oversize", "timeout"])
async def test_provider_bounds_response_and_transport_failures(monkeypatch, case):
    def handle(request):
        if case == "timeout":
            raise httpx.ReadTimeout("private request context", request=request)
        return httpx.Response(
            200, content=b"x" * (1_048_577 if case == "oversize" else 5)
        )

    adapter = make_adapter(monkeypatch, handle)
    try:
        with pytest.raises(TranscriptionUnavailableError):
            await adapter.transcribe(b"audio", "audio/wav")
    finally:
        await adapter.aclose()


def test_transcription_factory_uses_gemini_independently_of_text_provider(monkeypatch):
    monkeypatch.setenv("LLM_TEXT_PROVIDER", "deepseek")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_TRANSCRIPTION_MODEL", "gemini-3.5-transcribe")
    constructor = Mock()
    monkeypatch.setattr("app.llm.factory.GeminiAudioTranscriber", constructor)
    assert LLMProviderFactory.create_audio_transcriber() is constructor.return_value
    constructor.assert_called_once_with(
        "test-gemini-key", "gemini-3.5-transcribe", mode="smart"
    )
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        LLMProviderFactory.create_audio_transcriber()
