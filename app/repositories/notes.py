"""SQLAlchemy persistence queries for notes and their owning projects."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.locks import lock_project_processing
from app.models import (
    ChatMessageSource,
    Note,
    NoteConnection,
    NoteIdempotencyKey,
    NoteProcessingJob,
    Project,
    VectorCleanupRequest,
)


class NoteRepository:
    async def lock_project_processing(self, db: AsyncSession, project_id: UUID) -> None:
        await lock_project_processing(db, project_id)

    async def refresh_note(self, db: AsyncSession, note: Note) -> None:
        await db.refresh(note)

    async def add_note(self, db: AsyncSession, note: Note) -> None:
        db.add(note)
        await db.flush()

    def add_idempotency_key(
        self, db: AsyncSession, idempotency_key: NoteIdempotencyKey
    ) -> None:
        db.add(idempotency_key)

    def enqueue_processing(self, db: AsyncSession, note: Note) -> None:
        db.add(
            NoteProcessingJob(
                note_id=note.id,
                revision=note.revision,
                processing_generation=note.processing_generation,
            )
        )

    async def find_idempotency_key(
        self, db: AsyncSession, user_id: UUID, key: str
    ) -> NoteIdempotencyKey | None:
        return await db.scalar(
            select(NoteIdempotencyKey).where(
                NoteIdempotencyKey.user_id == user_id,
                NoteIdempotencyKey.key == key,
            )
        )

    async def get_note(self, db: AsyncSession, note_id: UUID) -> Note | None:
        return await db.get(Note, note_id)

    async def find_owned_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID, *, lock: bool = False
    ) -> Note | None:
        query = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def find_owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project | None:
        query = select(Project).where(
            Project.id == project_id, Project.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def list_for_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[Note]:
        result = await db.scalars(
            select(Note)
            .where(Note.user_id == user_id, Note.project_id == project_id)
            .order_by(Note.updated_at.desc(), Note.id)
        )
        return list(result)

    async def delete_with_owned_data(self, db: AsyncSession, note: Note) -> None:
        db.add(VectorCleanupRequest(note_id=note.id))
        await db.execute(
            delete(NoteConnection).where(
                (NoteConnection.source_note_id == note.id)
                | (NoteConnection.target_note_id == note.id)
            )
        )
        await db.execute(
            delete(ChatMessageSource).where(ChatMessageSource.note_id == note.id)
        )
        await db.execute(
            delete(NoteProcessingJob).where(NoteProcessingJob.note_id == note.id)
        )
        await db.delete(note)
        await db.flush()
