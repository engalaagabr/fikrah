"""HTTP presentation layer for semantic search."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.database import get_db_session
from app.infrastructure.container import search_service
from app.models import User
from app.search.errors import SearchUnavailableError
from app.search.schemas import SearchRequest, SearchResult
from app.search.service import SearchProjectNotFound

router = APIRouter(tags=["search"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


@router.post("/v1/projects/{project_id}/search", response_model=list[SearchResult])
async def search_project_notes(
    project_id: UUID,
    body: SearchRequest,
    user: AuthenticatedUser,
    db: Db,
) -> list[SearchResult]:
    try:
        matches = await search_service.retrieve(
            db, user.id, project_id, body.query, body.limit
        )
    except SearchProjectNotFound as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except SearchUnavailableError as error:
        raise HTTPException(
            status_code=503, detail="Semantic search is temporarily unavailable"
        ) from error
    return [
        SearchResult(
            note_id=match.note.id,
            title=match.note.title,
            content=match.note.content,
            score=match.score,
            updated_at=match.note.updated_at,
        )
        for match in matches
    ]
