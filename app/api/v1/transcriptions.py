"""Authenticated, stateless voice-to-text HTTP endpoint."""

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import (
    Db,
    LLMRequestBudget,
    TranscriptionServiceDependency,
)
from app.core.config import get_settings
from app.schemas.transcription import TranscriptionView
from app.services.transcription_errors import (
    AudioTooLarge,
    InvalidAudio,
    TranscriptionUnavailable,
    UnsupportedAudioType,
)

router = APIRouter(prefix="/v1/transcriptions", tags=["transcriptions"])


async def _read_audio(request: Request) -> tuple[bytes, str]:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "multipart/form-data"
    ):
        raise HTTPException(status_code=415, detail="Expected multipart/form-data")
    try:
        async with request.form(max_files=1, max_fields=0) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(status_code=422, detail="An audio file is required")
            return (
                await file.read(get_settings().fikrah_transcription_max_bytes + 1),
                file.content_type or "",
            )
    except StarletteHTTPException as error:
        if error.status_code != 400:
            raise
        raise HTTPException(status_code=422, detail="Invalid audio upload") from None


@router.post(
    "",
    response_model=TranscriptionView,
    responses={
        401: {"description": "Authentication required"},
        413: {"description": "Audio file or multipart body exceeds its limit"},
        415: {"description": "Unsupported request or audio media type"},
        422: {"description": "Invalid recording or multipart upload"},
        429: {"description": "LLM request budget exhausted"},
        503: {"description": "Transcription or request budget unavailable"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def transcribe_recording(
    request: Request,
    db: Db,
    budget: LLMRequestBudget,
    service: TranscriptionServiceDependency,
) -> TranscriptionView:
    """Return a SMART transcript in the recording's language, without creating a note."""
    # Authentication performed a read; release that transaction before Gemini runs.
    await db.rollback()
    audio, mime_type = await _read_audio(request)
    try:
        text = await service.transcribe(audio, mime_type)
    except AudioTooLarge:
        raise HTTPException(status_code=413, detail="Audio file is too large") from None
    except UnsupportedAudioType:
        raise HTTPException(
            status_code=415, detail="Unsupported audio media type"
        ) from None
    except InvalidAudio:
        raise HTTPException(
            status_code=422,
            detail="Audio is empty, invalid, or contains no transcribable speech",
        ) from None
    except TranscriptionUnavailable:
        raise HTTPException(
            status_code=503, detail="Audio transcription is temporarily unavailable"
        ) from None
    return TranscriptionView(text=text)
