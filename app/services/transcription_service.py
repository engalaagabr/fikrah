"""Validate a recording and obtain a transcript without storing user content."""

from collections.abc import Callable
from contextlib import aclosing

from app.llm.errors import AudioRejectedError, TranscriptionUnavailableError
from app.llm.ports import AudioTranscriber
from app.services.transcription_errors import (
    AudioTooLarge,
    InvalidAudio,
    TranscriptionUnavailable,
    UnsupportedAudioType,
)

_AUDIO_TYPES = {
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/mp3": "audio/mp3",
    "audio/mpeg": "audio/mpeg",
    "audio/mp4": "audio/m4a",
    "audio/m4a": "audio/m4a",
    "audio/x-m4a": "audio/m4a",
    "audio/aac": "audio/aac",
    "audio/ogg": "audio/ogg",
    "audio/flac": "audio/flac",
    "audio/webm": "audio/webm",
}


class TranscriptionService:
    def __init__(
        self,
        transcriber_factory: Callable[[], AudioTranscriber],
        max_audio_bytes: Callable[[], int],
    ) -> None:
        self._transcriber_factory = transcriber_factory
        self._max_audio_bytes = max_audio_bytes

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        if len(audio) > self._max_audio_bytes():
            raise AudioTooLarge
        if not audio:
            raise InvalidAudio
        normalized = _AUDIO_TYPES.get(mime_type.split(";", 1)[0].strip().lower())
        if normalized is None:
            raise UnsupportedAudioType
        try:
            async with aclosing(self._transcriber_factory()) as transcriber:
                text = await transcriber.transcribe(audio, normalized)
        except AudioRejectedError:
            raise InvalidAudio from None
        except (TranscriptionUnavailableError, RuntimeError):
            raise TranscriptionUnavailable from None
        if not text.strip():
            raise InvalidAudio
        return text
