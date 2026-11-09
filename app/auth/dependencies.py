"""Authentication dependencies shared by HTTP modules."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.database import get_db_session
from app.models import User

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
