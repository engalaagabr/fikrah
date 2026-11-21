"""Project-scoped semantic retrieval use case."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.search import SearchMatch
from app.llm.ports import EmbeddingModel
from app.rag.retriever import retrieve_current_notes
from app.repositories.search import SearchRepository
from app.services.search_errors import SearchProjectNotFound


class SemanticSearchService:
    def __init__(
        self,
        embedding_model_factory: Callable[[], EmbeddingModel],
        vector_search: Callable[
            [list[float], UUID, UUID, int], list[tuple[UUID, int, float]]
        ],
        repository: SearchRepository | None = None,
    ) -> None:
        self._embedding_model_factory = embedding_model_factory
        self._vector_search = vector_search
        self._repository = repository or SearchRepository()

    async def retrieve(
        self,
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID,
        query: str,
        limit: int,
    ) -> list[SearchMatch]:
        project = await self._repository.find_owned_project(db, user_id, project_id)
        if project is None:
            raise SearchProjectNotFound
        # Ownership is checked before external work; release the read transaction
        # while providers run, then validate their candidates in a fresh read.
        await db.rollback()
        try:
            return await retrieve_current_notes(
                db,
                user_id,
                project_id,
                query,
                limit,
                embedding_model_factory=self._embedding_model_factory,
                vector_search=self._vector_search,
                repository=self._repository,
            )
        finally:
            await db.rollback()
