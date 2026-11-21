"""Gemini Interactions transport for recorded audio transcription."""

import asyncio
import base64
import json
from typing import Literal

import httpx

from app.llm.errors import AudioRejectedError, TranscriptionUnavailableError

_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_MAX_RESPONSE_BYTES = 1_048_576


class GeminiAudioTranscriber:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        mode: Literal["verbatim", "smart"],
    ) -> None:
        self._model = model
        self._mode = mode
        self._client = httpx.AsyncClient(
            headers={"x-goog-api-key": api_key, "Api-Revision": "2026-05-20"},
            timeout=httpx.Timeout(90, connect=10),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        payload = {
            "model": self._model,
            "input": [
                {
                    "type": "audio",
                    "data": base64.b64encode(audio).decode("ascii"),
                    "mime_type": mime_type,
                }
            ],
            "generation_config": {
                "transcription_config": {"mode": {"type": self._mode}}
            },
            "store": False,
        }
        try:
            async with asyncio.timeout(90):
                async with self._client.stream(
                    "POST", _INTERACTIONS_URL, json=payload
                ) as response:
                    if response.status_code in {400, 422}:
                        raise AudioRejectedError
                    if response.status_code != 200:
                        raise TranscriptionUnavailableError
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65_536):
                        body.extend(chunk)
                        if len(body) > _MAX_RESPONSE_BYTES:
                            raise TranscriptionUnavailableError
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("status") != "completed":
                raise TranscriptionUnavailableError
            texts = []
            for step in data["steps"]:
                if step["type"] == "model_output":
                    for content in step["content"]:
                        if content["type"] == "text":
                            text = content["text"]
                            if not isinstance(text, str):
                                raise TranscriptionUnavailableError
                            texts.append(text)
            if not texts:
                raise TranscriptionUnavailableError
            return "".join(texts)
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            raise TranscriptionUnavailableError from None
