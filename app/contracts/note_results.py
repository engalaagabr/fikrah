"""Framework-independent results returned by note application use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NoteResult:
    id: UUID
    project_id: UUID
    title: str | None
    content: str
    concepts: tuple[str, ...]
    refinement_proposal: str | None
    revision: int
    processing_generation: int
    processing_status: str
    created_at: datetime
    updated_at: datetime
