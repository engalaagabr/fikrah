"""Persistence and vector boundaries used by note processing."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.contracts.processing import NoteProcessingSnapshot
from app.llm.contracts import NoteAnalysis


class NoteProcessingRepository(Protocol):
    def claim(
        self, job_id: UUID, worker_task_id: str, stale_before: datetime
    ) -> NoteProcessingSnapshot | None: ...

    def complete_if_current(
        self,
        snapshot: NoteProcessingSnapshot,
        analysis: NoteAnalysis,
        persist_vector: Callable[[], None],
    ) -> bool: ...

    def fail_if_current(
        self, snapshot: NoteProcessingSnapshot, *, terminal: bool
    ) -> bool: ...


class NoteVectorStore(Protocol):
    def upsert_note(
        self,
        note_id: UUID,
        vector: list[float],
        *,
        user_id: UUID,
        project_id: UUID,
        revision: int,
        processing_generation: int,
    ) -> None: ...
