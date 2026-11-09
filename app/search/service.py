"""Project-scoped semantic retrieval use case."""

from dataclasses import dataclass
import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.factory import AIProviderFactory
from app.infrastructure.vector_store.qdrant import SearchUnavailableError, search_note_vectors
from app.models import Note, Project


class SearchProjectNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SearchMatch:
    note: Note
    score: float


class SemanticSearchService:
    async def retrieve(
        self,
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> list[SearchMatch]:
        project = await db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        if project is None:
            raise SearchProjectNotFound

        try:
            embedding_model = AIProviderFactory.create_embedding_model()
            query_vector = await asyncio.to_thread(embedding_model.embed_query, query)
            matches = await asyncio.to_thread(
                search_note_vectors, query_vector, user_id, project_id, limit
            )
        except Exception as exc:
            if isinstance(exc, SearchUnavailableError):
                raise
            raise SearchUnavailableError("Embedding or vector retrieval failed") from exc

        if not matches:
            return []
        revisions = {note_id: revision for note_id, revision, _ in matches}
        notes = await db.scalars(
            select(Note).where(
                Note.id.in_(revisions),
                Note.user_id == user_id,
                Note.project_id == project_id,
                Note.processing_status == "completed",
            )
        )
        current_notes = {
            note.id: note for note in notes if note.revision == revisions[note.id]
        }
        return [
            SearchMatch(note=current_notes[note_id], score=score)
            for note_id, _revision, score in matches
            if note_id in current_notes
        ]
