"""HTTP presentation layer for semantic search."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.deps import (
    AuthenticatedUser,
    Db,
    LLMRequestBudget,
    SearchServiceDependency,
)
from app.rag.errors import SearchUnavailableError
from app.schemas.search import SearchRequest, SearchResult
from app.services.contracts.search import SearchMatch
from app.services.search_errors import SearchProjectNotFound

router = APIRouter(tags=["search"])


@router.post("/v1/projects/{project_id}/search", response_model=list[SearchResult])
async def search_project_notes(
    project_id: UUID,
    body: SearchRequest,
    user: AuthenticatedUser,
    db: Db,
    budget: LLMRequestBudget,
    service: SearchServiceDependency,
) -> list[SearchResult]:
    try:
        matches = await service.retrieve(db, user.id, project_id, body.query, body.limit)
    except SearchProjectNotFound as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except SearchUnavailableError as error:
        raise HTTPException(
            status_code=503, detail="Semantic search is temporarily unavailable"
        ) from error
    return [_search_result_view(match) for match in matches]


def _search_result_view(match: SearchMatch) -> SearchResult:
    return SearchResult(
        note_id=match.note_id,
        title=match.title,
        content=match.content,
        score=match.score,
        updated_at=match.updated_at,
    )
