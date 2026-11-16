"""SQLAlchemy read queries for knowledge connections and project graphs."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, NoteConnection, Project


class KnowledgeConnectionRepository:
    async def find_owned_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID
    ) -> Note | None:
        return await db.scalar(
            select(Note).where(Note.id == note_id, Note.user_id == user_id)
        )

    async def list_note_connections(
        self, db: AsyncSession, note: Note, user_id: UUID
    ) -> list[tuple[Note, NoteConnection]]:
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
        return list(rows)

    async def find_owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> Project | None:
        return await db.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )

    async def list_completed_project_notes(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[Note]:
        result = await db.scalars(
            select(Note)
            .where(
                Note.user_id == user_id,
                Note.project_id == project_id,
                Note.processing_status == "completed",
            )
            .order_by(Note.updated_at.desc(), Note.id)
        )
        return list(result)

    async def list_connections_between(
        self, db: AsyncSession, note_ids: set[UUID]
    ) -> list[NoteConnection]:
        connections = await db.scalars(
            select(NoteConnection).where(
                NoteConnection.source_note_id.in_(note_ids),
                NoteConnection.target_note_id.in_(note_ids),
            )
        )
        return list(connections)
