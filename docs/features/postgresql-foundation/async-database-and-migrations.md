# Feature: PostgreSQL Foundation

## Purpose

Provide the Backend with an asynchronous PostgreSQL connection/session foundation and schema migration tooling. PostgreSQL remains the source of truth for application records; Qdrant remains responsible for embeddings and retrieval metadata.

## Technology Decisions

- SQLAlchemy 2.x async ORM/Core using the `asyncpg` driver.
- Alembic for versioned schema migrations.
- `DATABASE_URL` configures PostgreSQL. Keep credentials outside source control.
- A shared async engine and session factory are initialized once per process and disposed during FastAPI shutdown.
- `get_db_session` is available as a FastAPI dependency for database-backed endpoints.
- The declarative metadata is initially empty; product tables will be added when their requirements and contracts are agreed.

## Local Setup

Install dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Set a PostgreSQL SQLAlchemy async URL in `DATABASE_URL`, for example:

```bash
export DATABASE_URL='postgresql+asyncpg://<user>:<password>@<host>:5432/<database>'
```

Create a migration after adding approved SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

## Runtime Behavior

- When `DATABASE_URL` is configured, FastAPI initializes the connection pool during application startup and disposes it at shutdown.
- When `DATABASE_URL` is absent, the API can still start for database-independent routes such as `GET /health`; any database dependency use requires configuration.
- The health endpoint checks API process availability only. It does not currently report PostgreSQL or Qdrant readiness.
- Creating an engine does not establish a database connection immediately; PostgreSQL is contacted when a session performs database I/O.

## Scope Boundaries

This feature does not add product tables, authentication, CRUD endpoints, Qdrant integration, or cross-store synchronization. Those require their own requirements and feature designs.

## Verification

```bash
python -m pytest
```
