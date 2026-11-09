"""Project-scoped semantic search API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import AIProviderFactory
from app.auth.routes import current_user
from app.database import get_db_session
from app.models import Note, Project, User
from app.search.service import SearchUnavailableError, search_note_vectors

router = APIRouter(tags=["search"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("Search query cannot be blank")
        return query


class SearchResult(BaseModel):
    note_id: UUID
    title: str | None
    content: str
    score: float
    updated_at: datetime


@router.post("/v1/projects/{project_id}/search", response_model=list[SearchResult])
async def search_project_notes(
    project_id: UUID,
    body: SearchRequest,
    user: AuthenticatedUser,
    db: Db,
) -> list[SearchResult]:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        embedding_model = AIProviderFactory.create_embedding_model()
        query_vector = await run_in_threadpool(embedding_model.embed_query, body.query)
        matches = await run_in_threadpool(
            search_note_vectors, query_vector, user.id, project_id, body.limit
        )
    except (RuntimeError, SearchUnavailableError) as exc:
        raise HTTPException(status_code=503, detail="Semantic search is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Semantic search is temporarily unavailable") from exc

    if not matches:
        return []

    matching_revisions = {note_id: revision for note_id, revision, _ in matches}
    notes = await db.scalars(
        select(Note).where(
            Note.id.in_(matching_revisions),
            Note.user_id == user.id,
            Note.project_id == project_id,
            Note.processing_status == "completed",
        )
    )
    authorized_notes = {
        note.id: note
        for note in notes
        if note.revision == matching_revisions[note.id]
    }

    # Preserve Qdrant's relevance order after PostgreSQL ownership and revision checks.
    return [
        SearchResult(
            note_id=note.id,
            title=note.title,
            content=note.content,
            score=score,
            updated_at=note.updated_at,
        )
        for note_id, _, score in matches
        if (note := authorized_notes.get(note_id)) is not None
    ]
