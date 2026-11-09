"""Read-only project and note knowledge-connection APIs."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.routes import current_user
from app.database import get_db_session
from app.models import Note, NoteConnection, Project, User

router = APIRouter(tags=["knowledge graph"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


class RelatedNoteView(BaseModel):
    note_id: UUID
    title: str | None
    shared_concepts: list[str]
    updated_at: datetime


class GraphNode(BaseModel):
    id: UUID
    title: str | None
    concepts: list[str]
    updated_at: datetime


class GraphEdge(BaseModel):
    source_note_id: UUID
    target_note_id: UUID
    shared_concepts: list[str]


class ProjectGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def _shared_concepts(left: list[str], right: list[str]) -> list[str]:
    right_normalized = {concept.strip().casefold() for concept in right if concept.strip()}
    shared: dict[str, str] = {}
    for concept in left:
        normalized = concept.strip().casefold()
        if normalized and normalized in right_normalized:
            shared.setdefault(normalized, concept.strip())
    return sorted(shared.values(), key=str.casefold)


def _not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{resource} not found")


@router.get("/v1/notes/{note_id}/connections", response_model=list[RelatedNoteView])
async def list_note_connections(
    note_id: UUID,
    user: AuthenticatedUser,
    db: Db,
) -> list[RelatedNoteView]:
    note = await db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if note is None:
        raise _not_found("Note")
    if note.processing_status != "completed":
        return []

    rows = await db.execute(
        select(Note, NoteConnection)
        .join(
            NoteConnection,
            or_(NoteConnection.source_note_id == Note.id, NoteConnection.target_note_id == Note.id),
        )
        .where(
            Note.id != note.id,
            Note.user_id == user.id,
            Note.project_id == note.project_id,
            Note.processing_status == "completed",
            or_(NoteConnection.source_note_id == note.id, NoteConnection.target_note_id == note.id),
        )
        .order_by(Note.updated_at.desc(), Note.id)
    )
    results_by_id: dict[UUID, RelatedNoteView] = {}
    for related, _connection in rows:
        shared_concepts = _shared_concepts(note.concepts, related.concepts)
        if shared_concepts and related.id not in results_by_id:
            results_by_id[related.id] = RelatedNoteView(
                note_id=related.id,
                title=related.title,
                shared_concepts=shared_concepts,
                updated_at=related.updated_at,
            )
    return list(results_by_id.values())


@router.get("/v1/projects/{project_id}/knowledge-graph", response_model=ProjectGraph)
async def get_project_knowledge_graph(
    project_id: UUID,
    user: AuthenticatedUser,
    db: Db,
) -> ProjectGraph:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise _not_found("Project")

    notes = list(
        await db.scalars(
            select(Note)
            .where(
                Note.user_id == user.id,
                Note.project_id == project_id,
                Note.processing_status == "completed",
            )
            .order_by(Note.updated_at.desc(), Note.id)
        )
    )
    note_by_id = {note.id: note for note in notes}
    if not note_by_id:
        return ProjectGraph(nodes=[], edges=[])

    connections = await db.scalars(
        select(NoteConnection).where(
            NoteConnection.source_note_id.in_(note_by_id),
            NoteConnection.target_note_id.in_(note_by_id),
        )
    )
    edges_by_pair: dict[tuple[UUID, UUID], GraphEdge] = {}
    for connection in connections:
        source_id, target_id = sorted(
            (connection.source_note_id, connection.target_note_id), key=str
        )
        source = note_by_id[source_id]
        target = note_by_id[target_id]
        shared_concepts = _shared_concepts(source.concepts, target.concepts)
        if shared_concepts:
            edges_by_pair.setdefault(
                (source_id, target_id),
                GraphEdge(
                    source_note_id=source_id,
                    target_note_id=target_id,
                    shared_concepts=shared_concepts,
                ),
            )
    edges = list(edges_by_pair.values())
    edges.sort(key=lambda edge: (str(edge.source_note_id), str(edge.target_note_id)))
    nodes = [
        GraphNode(
            id=note.id,
            title=note.title,
            concepts=note.concepts,
            updated_at=note.updated_at,
        )
        for note in notes
    ]
    return ProjectGraph(nodes=nodes, edges=edges)
