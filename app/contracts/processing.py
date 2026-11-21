"""Immutable processing identity shared by orchestration and persistence."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NoteProcessingSnapshot:
    job_id: UUID
    note_id: UUID
    user_id: UUID
    project_id: UUID
    revision: int
    processing_generation: int
    content: str
    attempt_token: str
