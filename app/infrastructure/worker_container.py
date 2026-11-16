"""Composition root for Celery worker use cases and infrastructure adapters."""

from datetime import timedelta

from app.infrastructure.persistence.worker_notes import WorkerNoteProcessingRepository
from app.llm.factory import LLMProviderFactory
from app.rag.embeddings import create_embedding_model
from app.rag.pipeline import NoteProcessingService
from app.rag.vector_store import QdrantNoteVectorStore


def create_note_processing_service(
    stale_processing_after: timedelta,
) -> tuple[NoteProcessingService, WorkerNoteProcessingRepository]:
    repository = WorkerNoteProcessingRepository()
    service = NoteProcessingService(
        repository=repository,
        vector_store=QdrantNoteVectorStore(),
        text_generator_factory=LLMProviderFactory.create_text_generator,
        embedding_model_factory=create_embedding_model,
        stale_processing_after=stale_processing_after,
    )
    return service, repository
