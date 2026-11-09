"""Project-scoped conversations grounded in the user's current note vectors."""

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import AIProviderFactory, ChatHistoryMessage, ChatNoteContext
from app.auth.routes import current_user
from app.database import get_db_session
from app.models import (
    ChatConversation,
    ChatMessage,
    ChatMessageSource,
    Note,
    Project,
    User,
)
from app.search.service import search_note_vectors

router = APIRouter(tags=["chat"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]
CHAT_CONTEXT_LIMIT = 8
CHAT_HISTORY_LIMIT = 12


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message cannot be blank")
        return content


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class SourceView(BaseModel):
    note_id: UUID
    title: str | None


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    supported: bool | None
    sources: list[SourceView] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationView):
    messages: list[MessageView]


class MessageSubmission(BaseModel):
    conversation: ConversationView
    user_message: MessageView
    assistant_message: MessageView


async def _owned_project(db: AsyncSession, user_id: UUID, project_id: UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _owned_conversation(
    db: AsyncSession, user_id: UUID, conversation_id: UUID, *, lock: bool = False
) -> ChatConversation:
    query = select(ChatConversation).where(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = await db.scalar(query)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def _message_views(db: AsyncSession, messages: list[ChatMessage]) -> list[MessageView]:
    if not messages:
        return []
    sources = await db.execute(
        select(ChatMessageSource.message_id, Note.id, Note.title)
        .join(Note, Note.id == ChatMessageSource.note_id)
        .where(ChatMessageSource.message_id.in_([message.id for message in messages]))
    )
    sources_by_message: dict[UUID, list[SourceView]] = {}
    for message_id, note_id, title in sources:
        sources_by_message.setdefault(message_id, []).append(
            SourceView(note_id=note_id, title=title)
        )
    return [
        MessageView.model_validate(message).model_copy(
            update={"sources": sources_by_message.get(message.id, [])}
        )
        for message in messages
    ]


@router.get("/v1/projects/{project_id}/conversations", response_model=list[ConversationView])
async def list_conversations(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> list[ConversationView]:
    await _owned_project(db, user.id, project_id)
    conversations = await db.scalars(
        select(ChatConversation)
        .where(ChatConversation.user_id == user.id, ChatConversation.project_id == project_id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id)
    )
    return [ConversationView.model_validate(item) for item in conversations]


@router.post(
    "/v1/projects/{project_id}/conversations",
    response_model=ConversationView,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    project_id: UUID,
    body: ConversationCreate,
    user: AuthenticatedUser,
    db: Db,
) -> ConversationView:
    await _owned_project(db, user.id, project_id)
    conversation = ChatConversation(
        user_id=user.id,
        project_id=project_id,
        title=body.title,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationView.model_validate(conversation)


@router.get("/v1/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> ConversationDetail:
    conversation = await _owned_conversation(db, user.id, conversation_id)
    messages = list(
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
    )
    return ConversationDetail(
        **ConversationView.model_validate(conversation).model_dump(),
        messages=await _message_views(db, messages),
    )


@router.post(
    "/v1/conversations/{conversation_id}/messages",
    response_model=MessageSubmission,
)
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    user: AuthenticatedUser,
    db: Db,
) -> MessageSubmission:
    conversation = await _owned_conversation(db, user.id, conversation_id, lock=True)
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

    try:
        embedding_model = AIProviderFactory.create_embedding_model()
        query_vector = await run_in_threadpool(embedding_model.embed_query, body.content)
        matches = await run_in_threadpool(
            search_note_vectors,
            query_vector,
            user.id,
            conversation.project_id,
            CHAT_CONTEXT_LIMIT,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Project knowledge is temporarily unavailable"
        ) from exc

    matching_revisions = {note_id: revision for note_id, revision, _ in matches}
    authorized_notes: dict[UUID, Note] = {}
    if matching_revisions:
        notes = await db.scalars(
            select(Note).where(
                Note.id.in_(matching_revisions),
                Note.user_id == user.id,
                Note.project_id == conversation.project_id,
                Note.processing_status == "completed",
            )
        )
        authorized_notes = {
            note.id: note
            for note in notes
            if note.revision == matching_revisions[note.id]
        }

    ordered_notes = [
        authorized_notes[note_id]
        for note_id, _, _ in matches
        if note_id in authorized_notes
    ]
    note_context = [
        ChatNoteContext(
            note_id=str(note.id),
            title=note.title or "Untitled note",
            content=note.content,
        )
        for note in ordered_notes
    ]

    try:
        text_model = AIProviderFactory.create_text_model()
        answer = await run_in_threadpool(
            text_model.answer_question,
            body.content,
            note_context,
            history,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="AI chat is temporarily unavailable") from exc

    valid_sources: list[UUID] = []
    if answer.supported:
        available_ids = set(authorized_notes)
        for source_id in answer.source_note_ids:
            try:
                parsed_id = UUID(source_id)
            except (TypeError, ValueError):
                continue
            if parsed_id in available_ids and parsed_id not in valid_sources:
                valid_sources.append(parsed_id)

    supported = answer.supported and bool(valid_sources)
    answer_content = answer.answer.strip()
    if not supported and answer.supported:
        answer_content = "I couldn't find an answer supported by your project notes."
    elif not answer_content:
        supported = False
        answer_content = "I couldn't find an answer supported by your project notes."

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

    user_view, assistant_view = await _message_views(
        db, [user_message, assistant_message]
    )
    return MessageSubmission(
        conversation=ConversationView.model_validate(conversation),
        user_message=user_view,
        assistant_message=assistant_view,
    )


@router.delete("/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> Response:
    conversation = await _owned_conversation(db, user.id, conversation_id, lock=True)
    message_ids = select(ChatMessage.id).where(ChatMessage.conversation_id == conversation.id)
    await db.execute(delete(ChatMessageSource).where(ChatMessageSource.message_id.in_(message_ids)))
    await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conversation.id))
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
