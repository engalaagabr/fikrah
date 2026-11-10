"""Framework-independent results for knowledge-connection use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RelatedNote:
    note_id: UUID
    title: str | None
    shared_concepts: tuple[str, ...]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeGraphNode:
    id: UUID
    title: str | None
    concepts: tuple[str, ...]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEdge:
    source_note_id: UUID
    target_note_id: UUID
    shared_concepts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectKnowledgeGraph:
    nodes: tuple[KnowledgeGraphNode, ...]
    edges: tuple[KnowledgeGraphEdge, ...]
