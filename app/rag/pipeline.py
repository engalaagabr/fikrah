"""Application use case for asynchronous note analysis and indexing."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.llm.ports import EmbeddingModel, StructuredTextGenerator
from app.llm.use_cases import analyze_note
from app.rag.ports import NoteProcessingRepository, NoteVectorStore


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

    def process(
        self, job_id: UUID, worker_task_id: str, *, terminal_on_error: bool = False
    ) -> None:
        now = datetime.now(timezone.utc)
        snapshot = self._repository.claim(
            job_id,
            f"{worker_task_id}:{uuid4()}",
            now - self._stale_processing_after,
        )
        if snapshot is None:
            return

        try:
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
        except Exception:
            self._repository.fail_if_current(snapshot, terminal=terminal_on_error)
            raise
