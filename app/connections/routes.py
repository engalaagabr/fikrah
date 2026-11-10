"""HTTP presentation layer for note-connection and graph retrieval."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.connections.contracts import (
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    ProjectKnowledgeGraph,
    RelatedNote,
)
from app.connections.schemas import (
    GraphEdge,
    GraphNode,
    ProjectGraph,
    RelatedNoteView,
)
from app.connections.service import (
    KnowledgeResourceNotFound,
)
from app.database import get_db_session
from app.infrastructure.container import knowledge_connection_service
from app.models import User

router = APIRouter(tags=["knowledge graph"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


@router.get("/v1/notes/{note_id}/connections", response_model=list[RelatedNoteView])
async def list_note_connections(
    note_id: UUID, user: AuthenticatedUser, db: Db
) -> list[RelatedNoteView]:
    try:
        related_notes = await knowledge_connection_service.list_note_connections(
            db, user.id, note_id
        )
    except KnowledgeResourceNotFound as error:
        raise HTTPException(status_code=404, detail=f"{error} not found") from error
    return [_related_note_view(note) for note in related_notes]


@router.get("/v1/projects/{project_id}/knowledge-graph", response_model=ProjectGraph)
async def get_project_knowledge_graph(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> ProjectGraph:
    try:
        graph = await knowledge_connection_service.get_project_graph(
            db, user.id, project_id
        )
    except KnowledgeResourceNotFound as error:
        raise HTTPException(status_code=404, detail=f"{error} not found") from error
    return _project_graph_view(graph)


def _related_note_view(note: RelatedNote) -> RelatedNoteView:
    return RelatedNoteView(
        note_id=note.note_id,
        title=note.title,
        shared_concepts=list(note.shared_concepts),
        updated_at=note.updated_at,
    )


def _project_graph_view(graph: ProjectKnowledgeGraph) -> ProjectGraph:
    return ProjectGraph(
        nodes=[_graph_node_view(node) for node in graph.nodes],
        edges=[_graph_edge_view(edge) for edge in graph.edges],
    )


def _graph_node_view(node: KnowledgeGraphNode) -> GraphNode:
    return GraphNode(
        id=node.id,
        title=node.title,
        concepts=list(node.concepts),
        updated_at=node.updated_at,
    )


def _graph_edge_view(edge: KnowledgeGraphEdge) -> GraphEdge:
    return GraphEdge(
        source_note_id=edge.source_note_id,
        target_note_id=edge.target_note_id,
        shared_concepts=list(edge.shared_concepts),
    )
