"""Retrieve Qdrant candidates and validate them against PostgreSQL."""

import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.search import SearchMatch
from app.llm.ports import EmbeddingModel
from app.rag.errors import SearchUnavailableError
from app.repositories.search import SearchRepository


async def retrieve_current_notes(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    query: str,
    limit: int,
    *,
    embedding_model_factory: Callable[[], EmbeddingModel],
    vector_search: Callable[
        [list[float], UUID, UUID, int], list[tuple[UUID, int, float]]
    ],
    repository: SearchRepository,
) -> list[SearchMatch]:
    """Return only vector matches still current and accessible in PostgreSQL."""
    try:
        embedding_model = embedding_model_factory()
        query_vector = await asyncio.to_thread(embedding_model.embed_query, query)
        matches = await asyncio.to_thread(
            vector_search, query_vector, user_id, project_id, limit
        )
    except Exception as exc:
        if isinstance(exc, SearchUnavailableError):
            raise
        raise SearchUnavailableError("Embedding or vector retrieval failed") from exc

    if not matches:
        return []
    revisions = {note_id: revision for note_id, revision, _ in matches}
    notes = await repository.find_completed_notes(
        db, user_id, project_id, set(revisions)
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
