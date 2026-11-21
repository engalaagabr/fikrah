"""Shared storage and prompt-input size validation."""

from app.core.config import get_settings


def validate_note_size(value: str) -> str:
    limit = get_settings().fikrah_note_max_characters
    if len(value) > limit:
        raise ValueError(f"Note text cannot exceed {limit} characters")
    return value
