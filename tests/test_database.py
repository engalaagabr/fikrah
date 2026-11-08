import asyncio

import pytest

from app.database import close_database, initialize_database


def test_initialize_database_creates_asyncpg_engine() -> None:
    database_url = "postgresql+asyncpg://user:pass@localhost/fikrah"
    factory = initialize_database(database_url)
    try:
        assert factory.kw["bind"].dialect.name == "postgresql"
        assert factory.kw["bind"].dialect.driver == "asyncpg"
        assert initialize_database(database_url) is factory
    finally:
        asyncio.run(close_database())


def test_initialize_database_requires_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        initialize_database()
