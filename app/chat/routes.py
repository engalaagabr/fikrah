"""HTTP presentation layer for project-scoped knowledge chat."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.chat.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationView,
    MessageCreate,
    MessageSubmission,
)
from app.chat.service import ChatService, ChatServiceError
from app.database import get_db_session
from app.models import User

router = APIRouter(tags=["chat"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]
chat_service = ChatService()
T = TypeVar("T")


@router.get("/v1/projects/{project_id}/conversations", response_model=list[ConversationView])
async def list_conversations(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> list[ConversationView]:
    return await _execute(chat_service.list_conversations(db, user.id, project_id))


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
    return await _execute(
        chat_service.create_conversation(db, user.id, project_id, body)
    )


@router.get("/v1/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> ConversationDetail:
    return await _execute(
        chat_service.get_conversation(db, user.id, conversation_id)
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
    return await _execute(
        chat_service.send_message(db, user.id, conversation_id, body)
    )


@router.delete("/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, user: AuthenticatedUser, db: Db
) -> Response:
    await _execute(chat_service.delete_conversation(db, user.id, conversation_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _execute(call: Awaitable[T]) -> T:
    try:
        return await call
    except ChatServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
