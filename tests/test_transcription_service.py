"""Transcription validation and asynchronous provider ownership."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.llm.errors import AudioRejectedError, TranscriptionUnavailableError
from app.services.transcription_errors import (
    AudioTooLarge,
    InvalidAudio,
    TranscriptionUnavailable,
    UnsupportedAudioType,
)
from app.services.transcription_service import TranscriptionService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("audio", "mime", "error"),
    [
        (b"", "audio/wav", InvalidAudio),
        (b"x" * 11, "audio/wav", AudioTooLarge),
        (b"audio", "image/png", UnsupportedAudioType),
        (b"audio", "", UnsupportedAudioType),
    ],
)
async def test_validation_precedes_provider_creation(audio, mime, error):
    factory = Mock()
    service = TranscriptionService(factory, lambda: 10)
    with pytest.raises(error):
        await service.transcribe(audio, mime)
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime", "normalized"),
    [
        ("audio/x-wav", "audio/wav"),
        ("audio/mp4", "audio/m4a"),
        ("audio/ogg; codecs=opus", "audio/ogg"),
    ],
)
async def test_service_normalizes_audio_types_and_closes_owned_client(mime, normalized):
    provider = SimpleNamespace(
        transcribe=AsyncMock(return_value="النص الأصلي"), aclose=AsyncMock()
    )
    service = TranscriptionService(lambda: provider, lambda: 10)
    assert await service.transcribe(b"audio", mime) == "النص الأصلي"
    provider.transcribe.assert_awaited_once_with(b"audio", normalized)
    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (AudioRejectedError(), InvalidAudio),
        (TranscriptionUnavailableError(), TranscriptionUnavailable),
    ],
)
async def test_service_closes_client_on_failure(failure, expected):
    provider = SimpleNamespace(
        transcribe=AsyncMock(side_effect=failure), aclose=AsyncMock()
    )
    with pytest.raises(expected):
        await TranscriptionService(lambda: provider, lambda: 10).transcribe(
            b"audio", "audio/wav"
        )
    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_reports_missing_configuration_and_silent_audio():
    def missing():
        raise RuntimeError("private configuration context")

    with pytest.raises(TranscriptionUnavailable):
        await TranscriptionService(missing, lambda: 10).transcribe(
            b"audio", "audio/wav"
        )
    provider = SimpleNamespace(
        transcribe=AsyncMock(return_value="  "), aclose=AsyncMock()
    )
    with pytest.raises(InvalidAudio):
        await TranscriptionService(lambda: provider, lambda: 10).transcribe(
            b"audio", "audio/wav"
        )
    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_closes_client_when_cancelled():
    started = asyncio.Event()

    async def pending(*_):
        started.set()
        await asyncio.sleep(60)

    provider = SimpleNamespace(transcribe=pending, aclose=AsyncMock())
    task = asyncio.create_task(
        TranscriptionService(lambda: provider, lambda: 10).transcribe(
            b"audio", "audio/wav"
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    provider.aclose.assert_awaited_once()
