"""HTTP response schemas for related notes and project graph endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
