"""Application use case for asynchronous note analysis and indexing."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from app.llm.contracts import NoteAnalysis
from app.llm.ports import EmbeddingModel, StructuredTextGenerator
from app.llm.use_cases import analyze_note


@dataclass(frozen=True, slots=True)
class NoteProcessingSnapshot:
    job_id: UUID
    note_id: UUID
    user_id: UUID
    project_id: UUID
    revision: int
    processing_generation: int
    content: str


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


class NoteProcessingService:
    def __init__(
        self,
        repository: NoteProcessingRepository,
        vector_store: NoteVectorStore,
        text_generator_factory: Callable[[], StructuredTextGenerator],
        embedding_model_factory: Callable[[], EmbeddingModel],
        stale_processing_after: timedelta,
    ) -> None:
        self._repository = repository
        self._vector_store = vector_store
        self._text_generator_factory = text_generator_factory
        self._embedding_model_factory = embedding_model_factory
        self._stale_processing_after = stale_processing_after

    def process(self, job_id: UUID, worker_task_id: str) -> None:
        now = datetime.now(timezone.utc)
        snapshot = self._repository.claim(
            job_id,
            worker_task_id,
            now - self._stale_processing_after,
        )
        if snapshot is None:
            return

        analysis = analyze_note(self._text_generator_factory(), snapshot.content)
        embedding = self._embedding_model_factory().embed_note(snapshot.content)

        def persist_vector() -> None:
            self._vector_store.upsert_note(
                snapshot.note_id,
                embedding,
                user_id=snapshot.user_id,
                project_id=snapshot.project_id,
                revision=snapshot.revision,
                processing_generation=snapshot.processing_generation,
            )

        self._repository.complete_if_current(snapshot, analysis, persist_vector)
