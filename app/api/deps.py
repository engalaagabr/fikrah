"""Authentication dependencies shared by HTTP modules."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models import User
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.connections_service import KnowledgeConnectionService
from app.services.notes_service import NoteService
from app.services.projects_service import ProjectService
from app.services.search_service import SemanticSearchService

bearer = HTTPBearer(auto_error=False)
Db = Annotated[AsyncSession, Depends(get_db_session)]


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Db,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(credentials.credentials)
    except (InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


AuthenticatedUser = Annotated[User, Depends(current_user)]


def get_auth_service() -> AuthService:
    from app.infrastructure.container import auth_service

    return auth_service


def get_chat_service() -> ChatService:
    from app.infrastructure.container import chat_service

    return chat_service


def get_connection_service() -> KnowledgeConnectionService:
    from app.infrastructure.container import knowledge_connection_service

    return knowledge_connection_service


def get_note_service() -> NoteService:
    from app.infrastructure.container import note_service

    return note_service


def get_project_service() -> ProjectService:
    from app.infrastructure.container import project_service

    return project_service


def get_search_service() -> SemanticSearchService:
    from app.infrastructure.container import search_service

    return search_service


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
ConnectionServiceDependency = Annotated[
    KnowledgeConnectionService, Depends(get_connection_service)
]
NoteServiceDependency = Annotated[NoteService, Depends(get_note_service)]
ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]
SearchServiceDependency = Annotated[
    SemanticSearchService, Depends(get_search_service)
]
