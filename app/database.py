"""PostgreSQL engine and async session lifecycle."""

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL_ENV = "DATABASE_URL"

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def initialize_database(
    database_url: str | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create the shared async engine and session factory once per process."""
    global _engine, _session_factory

    resolved_url = database_url or os.getenv(DATABASE_URL_ENV)
    if not resolved_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} must be configured to use PostgreSQL")

    if _engine is not None:
        if _engine.url.render_as_string(hide_password=False) != resolved_url:
            raise RuntimeError("PostgreSQL is already initialized with a different URL")
        assert _session_factory is not None
        return _session_factory

    _engine = create_async_engine(resolved_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session for a FastAPI dependency."""
    if _session_factory is None:
        initialize_database()

    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


async def close_database() -> None:
    """Dispose of the engine and clear its process-level references."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None
