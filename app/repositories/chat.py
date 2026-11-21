"""SQLAlchemy read queries for project conversation history."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChatConversation,
    ChatMessage,
    ChatMessageSource,
    Note,
    Project,
)


class ChatRepository:
    async def refresh_conversation(
        self, db: AsyncSession, conversation: ChatConversation
    ) -> None:
        await db.refresh(conversation)

    async def refresh_message(self, db: AsyncSession, message: ChatMessage) -> None:
        await db.refresh(message)

    async def add_conversation(
        self, db: AsyncSession, conversation: ChatConversation
    ) -> None:
        db.add(conversation)
        await db.flush()

    async def add_messages_with_sources(
        self,
        db: AsyncSession,
        user_message: ChatMessage,
        assistant_message: ChatMessage,
        source_note_ids: list[UUID],
        *,
        supported: bool,
    ) -> None:
        db.add_all([user_message, assistant_message])
        await db.flush()
        db.add_all(
            ChatMessageSource(message_id=assistant_message.id, note_id=note_id)
            for note_id in source_note_ids
            if supported
        )

    async def find_owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project | None:
        query = select(Project).where(
            Project.id == project_id, Project.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def find_owned_conversation(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        *,
        lock: bool = False,
    ) -> ChatConversation | None:
        query = select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    async def list_message_sources(
        self, db: AsyncSession, messages: list[ChatMessage]
    ) -> list[tuple[UUID, UUID, str | None]]:
        rows = await db.execute(
            select(ChatMessageSource.message_id, Note.id, Note.title)
            .join(Note, Note.id == ChatMessageSource.note_id)
            .where(
                ChatMessageSource.message_id.in_([message.id for message in messages])
            )
        )
        return list(rows)

    async def list_conversations(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[ChatConversation]:
        rows = await db.scalars(
            select(ChatConversation)
            .where(
                ChatConversation.user_id == user_id,
                ChatConversation.project_id == project_id,
            )
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id)
        )
        return list(rows)

    async def list_messages(
        self, db: AsyncSession, conversation_id: UUID
    ) -> list[ChatMessage]:
        messages = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
        return list(messages)

    async def list_recent_messages(
        self, db: AsyncSession, conversation_id: UUID, limit: int
    ) -> list[ChatMessage]:
        messages = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        return list(messages)

    async def latest_message_id(
        self, db: AsyncSession, conversation_id: UUID
    ) -> UUID | None:
        return await db.scalar(
            select(ChatMessage.id)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )

    async def find_completed_notes_for_citations(
        self,
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID,
        note_ids: list[UUID],
    ) -> list[Note]:
        notes = await db.scalars(
            select(Note)
            .where(
                Note.id.in_(note_ids),
                Note.user_id == user_id,
                Note.project_id == project_id,
                Note.processing_status == "completed",
            )
            .order_by(Note.id)
            .with_for_update()
        )
        return list(notes)

    async def delete_conversation_with_messages(
        self, db: AsyncSession, conversation: ChatConversation
    ) -> None:
        message_ids = select(ChatMessage.id).where(
            ChatMessage.conversation_id == conversation.id
        )
        await db.execute(
            delete(ChatMessageSource).where(
                ChatMessageSource.message_id.in_(message_ids)
            )
        )
        await db.execute(
            delete(ChatMessage).where(
                ChatMessage.conversation_id == conversation.id
            )
        )
        await db.delete(conversation)
        await db.flush()
