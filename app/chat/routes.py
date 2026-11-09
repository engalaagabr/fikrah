"""HTTP presentation layer for project-scoped knowledge chat."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.chat.contracts import (
    ConversationCreateCommand,
    ConversationSummary,
    MessageCreateCommand,
    MessageRecord,
    SourceReference,
)
from app.chat.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationView,
    MessageCreate,
    MessageSubmission,
    MessageView,
    SourceView,
)
from app.chat.service import ChatServiceError
from app.database import get_db_session
from app.infrastructure.container import chat_service
from app.models import User

router = APIRouter(tags=["chat"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]
T = TypeVar("T")


@router.get(
    "/v1/projects/{project_id}/conversations", response_model=list[ConversationView]
)
async def list_conversations(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> list[ConversationView]:
    conversations = await _execute(
        chat_service.list_conversations(db, user.id, project_id)
    )
    return [_conversation_view(item) for item in conversations]


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
    conversation = await _execute(
        chat_service.create_conversation(
            db,
            user.id,
            project_id,
            ConversationCreateCommand(title=body.title),
        )
    )
    return _conversation_view(conversation)


@router.get("/v1/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> ConversationDetail:
    conversation = await _execute(
        chat_service.get_conversation(db, user.id, conversation_id)
    )
    return ConversationDetail(
        **_conversation_view(conversation.conversation).model_dump(),
        messages=[_message_view(message) for message in conversation.messages],
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
    submission = await _execute(
        chat_service.send_message(
            db,
            user.id,
            conversation_id,
            MessageCreateCommand(content=body.content),
        )
    )
    return MessageSubmission(
        conversation=_conversation_view(submission.conversation),
        user_message=_message_view(submission.user_message),
        assistant_message=_message_view(submission.assistant_message),
    )


@router.delete(
    "/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> Response:
    await _execute(chat_service.delete_conversation(db, user.id, conversation_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _execute(call: Awaitable[T]) -> T:
    try:
        return await call
    except ChatServiceError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.detail
        ) from error


def _conversation_view(value: ConversationSummary) -> ConversationView:
    return ConversationView(
        id=value.id,
        project_id=value.project_id,
        title=value.title,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _message_view(value: MessageRecord) -> MessageView:
    return MessageView(
        id=value.id,
        role=value.role,
        content=value.content,
        supported=value.supported,
        sources=[_source_view(source) for source in value.sources],
        created_at=value.created_at,
    )


def _source_view(value: SourceReference) -> SourceView:
    return SourceView(note_id=value.note_id, title=value.title)
