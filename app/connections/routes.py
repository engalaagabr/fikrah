"""HTTP presentation layer for note-connection and graph retrieval."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.connections.schemas import ProjectGraph, RelatedNoteView
from app.connections.service import (
    KnowledgeConnectionService,
    KnowledgeResourceNotFound,
)
from app.database import get_db_session
from app.models import User

router = APIRouter(tags=["knowledge graph"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]
knowledge_service = KnowledgeConnectionService()


@router.get("/v1/notes/{note_id}/connections", response_model=list[RelatedNoteView])
async def list_note_connections(
    note_id: UUID, user: AuthenticatedUser, db: Db
) -> list[RelatedNoteView]:
    try:
        return await knowledge_service.list_note_connections(db, user.id, note_id)
    except KnowledgeResourceNotFound as error:
        raise HTTPException(status_code=404, detail=f"{error} not found") from error


@router.get("/v1/projects/{project_id}/knowledge-graph", response_model=ProjectGraph)
async def get_project_knowledge_graph(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> ProjectGraph:
    try:
        return await knowledge_service.get_project_graph(db, user.id, project_id)
    except KnowledgeResourceNotFound as error:
        raise HTTPException(status_code=404, detail=f"{error} not found") from error
