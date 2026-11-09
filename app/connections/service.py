"""Knowledge-connection read use cases and ownership rules."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connections.schemas import GraphEdge, GraphNode, ProjectGraph, RelatedNoteView
from app.models import Note, NoteConnection, Project


class KnowledgeResourceNotFound(Exception):
    pass


def _shared_concepts(left: list[str], right: list[str]) -> list[str]:
    right_normalized = {
        concept.strip().casefold() for concept in right if concept.strip()
    }
    shared: dict[str, str] = {}
    for concept in left:
        normalized = concept.strip().casefold()
        if normalized and normalized in right_normalized:
            shared.setdefault(normalized, concept.strip())
    return sorted(shared.values(), key=str.casefold)


class KnowledgeConnectionService:
    async def list_note_connections(
        self, db: AsyncSession, user_id: UUID, note_id: UUID
    ) -> list[RelatedNoteView]:
        note = await db.scalar(
            select(Note).where(Note.id == note_id, Note.user_id == user_id)
        )
        if note is None:
            raise KnowledgeResourceNotFound("Note")
        if note.processing_status != "completed":
            return []

        rows = await db.execute(
            select(Note, NoteConnection)
            .join(
                NoteConnection,
                or_(
                    NoteConnection.source_note_id == Note.id,
                    NoteConnection.target_note_id == Note.id,
                ),
            )
            .where(
                Note.id != note.id,
                Note.user_id == user_id,
                Note.project_id == note.project_id,
                Note.processing_status == "completed",
                or_(
                    NoteConnection.source_note_id == note.id,
                    NoteConnection.target_note_id == note.id,
                ),
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

    async def get_project_graph(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> ProjectGraph:
        project = await db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        if project is None:
            raise KnowledgeResourceNotFound("Project")

        notes = list(
            await db.scalars(
                select(Note)
                .where(
                    Note.user_id == user_id,
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

        edges = sorted(
            edges_by_pair.values(),
            key=lambda edge: (str(edge.source_note_id), str(edge.target_note_id)),
        )
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
