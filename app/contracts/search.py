"""Framework-independent results returned by semantic search use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SearchMatch:
    note_id: UUID
    title: str | None
    content: str
    revision: int
    score: float
    updated_at: datetime
