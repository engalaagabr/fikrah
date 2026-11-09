# Phase: Backend Foundation

## Goal

Create the smallest runnable foundation for the FIKRAH Backend using the user-selected FastAPI framework.

## Scope

- Establish the Python/FastAPI application entry point.
- Provide a basic operational health endpoint.
- PostgreSQL and Qdrant have been selected. PostgreSQL is the source of truth for application records; Qdrant stores embeddings and retrieval metadata.
- PostgreSQL access uses SQLAlchemy 2.x async with the `asyncpg` driver, and Alembic manages schema migrations. Product tables remain out of scope until their requirements are defined.
- Redis is the broker for Backend-owned asynchronous note-processing jobs, with Celery selected as the worker. Redis durability, retries, and deployment configuration remain open.
- Cross-store synchronization and recovery behavior remain open until designed.
- Authentication and account behavior are implemented in the separate Account Access phase.

## Not Included Yet

- Product CRUD and AI workflows.
- Product persistence models, authentication, and CRUD behavior. The connection/session infrastructure and migration tooling are covered by the PostgreSQL foundation feature.
- AI provider integration or note-processing workflows.
- Product endpoints for notes, projects, search, graph, or chat.

## Completion Criteria

- The API application can be started locally.
- The health endpoint returns a simple status response.
- Feature and phase documentation are maintained in English by default.

## Local Environment

The FastAPI application and Celery worker load a root `.env` file through
`python-dotenv`. The file is local and ignored by Git; environment variables
already supplied by the host take precedence. Local setup and supported
variables are documented in [`local-environment-configuration`](../../features/local-environment-configuration/overview.md).
The local PostgreSQL, Redis, and Qdrant containers are defined in
[`local-development-stack`](../../features/local-development-stack/overview.md).
