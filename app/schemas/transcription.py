"""Public response for synchronous recording transcription."""

from pydantic import BaseModel


class TranscriptionView(BaseModel):
    text: str
