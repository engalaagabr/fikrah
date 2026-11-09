"""SQLAlchemy persistence operations for projects and project-owned data."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChatConversation,
    ChatMessage,
    ChatMessageSource,
    Note,
    NoteConnection,
    NoteProcessingJob,
    Project,
    VectorCleanupRequest,
)


class ProjectRepository:
    async def list_for_user(self, db: AsyncSession, user_id: UUID) -> list[Project]:
        result = await db.scalars(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.is_general.desc(), Project.created_at, Project.id)
        )
        return list(result)

    async def find_owned(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project | None:
        query = select(Project).where(
            Project.id == project_id, Project.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def create(self, db: AsyncSession, user_id: UUID, name: str) -> Project:
        project = Project(user_id=user_id, name=name, is_general=False)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    async def save(self, db: AsyncSession, project: Project) -> Project:
        await db.commit()
        await db.refresh(project)
        return project

    async def delete_with_owned_data(self, db: AsyncSession, project: Project) -> None:
        note_ids = list(
            await db.scalars(select(Note.id).where(Note.project_id == project.id))
        )
        db.add_all(VectorCleanupRequest(note_id=note_id) for note_id in note_ids)

        conversation_ids = select(ChatConversation.id).where(
            ChatConversation.project_id == project.id
        )
        message_ids = select(ChatMessage.id).where(
            ChatMessage.conversation_id.in_(conversation_ids)
        )
        await db.execute(
            delete(ChatMessageSource).where(
                ChatMessageSource.message_id.in_(message_ids)
            )
        )
        await db.execute(
            delete(ChatMessage).where(ChatMessage.conversation_id.in_(conversation_ids))
        )
        await db.execute(
            delete(ChatConversation).where(ChatConversation.project_id == project.id)
        )

        if note_ids:
            await db.execute(
                delete(NoteConnection).where(
                    NoteConnection.source_note_id.in_(note_ids)
                    | NoteConnection.target_note_id.in_(note_ids)
                )
            )
            await db.execute(
                delete(NoteProcessingJob).where(NoteProcessingJob.note_id.in_(note_ids))
            )
            await db.execute(delete(Note).where(Note.id.in_(note_ids)))

        await db.delete(project)
        await db.commit()
