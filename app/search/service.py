"""Project-scoped semantic retrieval use case."""

import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ports import EmbeddingModel
from app.models import Note, Project
from app.search.contracts import SearchMatch
from app.search.errors import SearchUnavailableError


class SearchProjectNotFound(Exception):
    pass


class SemanticSearchService:
    def __init__(
        self,
        embedding_model_factory: Callable[[], EmbeddingModel],
        vector_search: Callable[
            [list[float], UUID, UUID, int], list[tuple[UUID, int, float]]
        ],
    ) -> None:
        self._embedding_model_factory = embedding_model_factory
        self._vector_search = vector_search

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
            embedding_model = self._embedding_model_factory()
            query_vector = await asyncio.to_thread(embedding_model.embed_query, query)
            matches = await asyncio.to_thread(
                self._vector_search, query_vector, user_id, project_id, limit
            )
        except Exception as exc:
            if isinstance(exc, SearchUnavailableError):
                raise
            raise SearchUnavailableError(
                "Embedding or vector retrieval failed"
            ) from exc

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
            SearchMatch(
                note_id=note_id,
                title=current_notes[note_id].title,
                content=current_notes[note_id].content,
                revision=current_notes[note_id].revision,
                score=score,
                updated_at=current_notes[note_id].updated_at,
            )
            for note_id, _revision, score in matches
            if note_id in current_notes
        ]
