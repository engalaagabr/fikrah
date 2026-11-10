"""Project chat use cases, retrieval orchestration, and persistence rules."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.contracts import (
    ConversationCreateCommand,
    ConversationHistory,
    ConversationSummary,
    MessageCreateCommand,
    MessageRecord,
    MessageSubmissionResult,
    SourceReference,
)
from app.llm.contracts import ChatHistoryMessage, ChatNoteContext
from app.llm.ports import StructuredTextGenerator
from app.llm.use_cases import answer_project_question
from app.models import ChatConversation, ChatMessage, ChatMessageSource, Note, Project
from app.search.errors import SearchUnavailableError
from app.search.service import SearchProjectNotFound, SemanticSearchService

CHAT_CONTEXT_LIMIT = 8
CHAT_HISTORY_LIMIT = 12


class ChatServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ChatService:
    def __init__(
        self,
        search_service: SemanticSearchService,
        text_generator_factory: Callable[[], StructuredTextGenerator],
    ) -> None:
        self._search_service = search_service
        self._text_generator_factory = text_generator_factory

    async def _owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project:
        query = select(Project).where(
            Project.id == project_id, Project.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        project = await db.scalar(query)
        if project is None:
            raise ChatServiceError(404, "Project not found")
        return project

    async def _owned_conversation(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        *,
        lock: bool = False,
    ) -> ChatConversation:
        query = select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        conversation = await db.scalar(query)
        if conversation is None:
            raise ChatServiceError(404, "Conversation not found")
        return conversation

    async def _message_views(
        self, db: AsyncSession, messages: list[ChatMessage]
    ) -> list[MessageRecord]:
        if not messages:
            return []
        rows = await db.execute(
            select(ChatMessageSource.message_id, Note.id, Note.title)
            .join(Note, Note.id == ChatMessageSource.note_id)
            .where(
                ChatMessageSource.message_id.in_([message.id for message in messages])
            )
        )
        sources_by_message: dict[UUID, list[SourceReference]] = {}
        for message_id, note_id, title in rows:
            sources_by_message.setdefault(message_id, []).append(
                SourceReference(note_id=note_id, title=title)
            )
        return [
            MessageRecord(
                id=message.id,
                role=message.role,
                content=message.content,
                supported=message.supported,
                sources=tuple(sources_by_message.get(message.id, [])),
                created_at=message.created_at,
            )
            for message in messages
        ]

    async def list_conversations(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[ConversationSummary]:
        await self._owned_project(db, user_id, project_id)
        rows = await db.scalars(
            select(ChatConversation)
            .where(
                ChatConversation.user_id == user_id,
                ChatConversation.project_id == project_id,
            )
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id)
        )
        return [self._conversation_summary(item) for item in rows]

    async def create_conversation(
        self,
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID,
        body: ConversationCreateCommand,
    ) -> ConversationSummary:
        await self._owned_project(db, user_id, project_id, lock=True)
        conversation = ChatConversation(
            user_id=user_id,
            project_id=project_id,
            title=body.title,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return self._conversation_summary(conversation)

    async def get_conversation(
        self, db: AsyncSession, user_id: UUID, conversation_id: UUID
    ) -> ConversationHistory:
        conversation = await self._owned_conversation(db, user_id, conversation_id)
        messages = list(
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        )
        return ConversationHistory(
            conversation=self._conversation_summary(conversation),
            messages=tuple(await self._message_views(db, messages)),
        )

    async def send_message(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        body: MessageCreateCommand,
    ) -> MessageSubmissionResult:
        conversation = await self._owned_conversation(
            db, user_id, conversation_id, lock=True
        )
        history_desc = list(
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(CHAT_HISTORY_LIMIT)
            )
        )
        history = [
            ChatHistoryMessage(role=message.role, content=message.content)
            for message in reversed(history_desc)
        ]
        project_id = conversation.project_id
        last_message_id = history_desc[0].id if history_desc else None
        await db.rollback()

        try:
            matches = await self._search_service.retrieve(
                db, user_id, project_id, body.content, CHAT_CONTEXT_LIMIT
            )
        except SearchProjectNotFound as error:
            raise ChatServiceError(404, "Project not found") from error
        except SearchUnavailableError as error:
            raise ChatServiceError(
                503, "Project knowledge is temporarily unavailable"
            ) from error

        note_context = [
            ChatNoteContext(
                note_id=str(match.note_id),
                title=match.title or "Untitled note",
                content=match.content,
            )
            for match in matches
        ]
        matching_revisions = {match.note_id: match.revision for match in matches}
        try:
            text_generator = self._text_generator_factory()
            answer = await asyncio.to_thread(
                answer_project_question,
                text_generator,
                body.content,
                note_context,
                history,
            )
        except Exception as error:
            raise ChatServiceError(
                503, "LLM chat is temporarily unavailable"
            ) from error

        conversation = await self._owned_conversation(
            db, user_id, conversation_id, lock=True
        )
        latest_message_id = await db.scalar(
            select(ChatMessage.id)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        if latest_message_id != last_message_id:
            await db.rollback()
            raise ChatServiceError(
                409,
                "The conversation changed while the answer was being generated. Retry the message.",
            )

        available_ids = set(matching_revisions)
        valid_sources: list[UUID] = []
        if answer.supported:
            for source_id in answer.source_note_ids:
                try:
                    parsed_id = UUID(source_id)
                except (TypeError, ValueError):
                    continue
                if parsed_id in available_ids and parsed_id not in valid_sources:
                    valid_sources.append(parsed_id)

        if valid_sources:
            source_notes = await db.scalars(
                select(Note)
                .where(
                    Note.id.in_(valid_sources),
                    Note.user_id == user_id,
                    Note.project_id == project_id,
                    Note.processing_status == "completed",
                )
                .with_for_update()
            )
            current_source_ids = {
                note.id
                for note in source_notes
                if note.revision == matching_revisions.get(note.id)
            }
            valid_sources = [
                note_id for note_id in valid_sources if note_id in current_source_ids
            ]

        supported = answer.supported and bool(valid_sources)
        answer_content = answer.answer.strip()
        if not supported and answer.supported:
            answer_content = (
                "I couldn't find an answer supported by your project notes."
            )
        elif not answer_content:
            supported = False
            answer_content = (
                "I couldn't find an answer supported by your project notes."
            )

        now = datetime.now(timezone.utc)
        user_message = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=body.content,
            created_at=now,
        )
        assistant_message = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer_content,
            supported=supported,
            created_at=now + timedelta(microseconds=1),
        )
        if conversation.title is None:
            conversation.title = body.content[:120]
        db.add_all([user_message, assistant_message])
        await db.flush()
        db.add_all(
            ChatMessageSource(message_id=assistant_message.id, note_id=note_id)
            for note_id in valid_sources
            if supported
        )
        await db.commit()
        await db.refresh(conversation)
        await db.refresh(user_message)
        await db.refresh(assistant_message)

        user_view, assistant_view = await self._message_views(
            db, [user_message, assistant_message]
        )
        return MessageSubmissionResult(
            conversation=self._conversation_summary(conversation),
            user_message=user_view,
            assistant_message=assistant_view,
        )

    @staticmethod
    def _conversation_summary(
        conversation: ChatConversation,
    ) -> ConversationSummary:
        return ConversationSummary(
            id=conversation.id,
            project_id=conversation.project_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    async def delete_conversation(
        self, db: AsyncSession, user_id: UUID, conversation_id: UUID
    ) -> None:
        conversation = await self._owned_conversation(
            db, user_id, conversation_id, lock=True
        )
        message_ids = select(ChatMessage.id).where(
            ChatMessage.conversation_id == conversation.id
        )
        await db.execute(
            delete(ChatMessageSource).where(
                ChatMessageSource.message_id.in_(message_ids)
            )
        )
        await db.execute(
            delete(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
        )
        await db.delete(conversation)
        await db.commit()
