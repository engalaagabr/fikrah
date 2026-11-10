# Local Development Stack

## Purpose

Run the complete local backend stack: PostgreSQL, Redis, Qdrant, the FastAPI
application, a Celery worker, and a Celery beat scheduler. This stack is for
backend development; it does not define production deployment or expose
services beyond the local machine.

## Services

| Service | Local endpoint | Persistence |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | Docker named volume |
| Redis | `localhost:6379` | Docker named volume with AOF (`appendfsync everysec`) |
| Qdrant HTTP API | `localhost:6333` | Docker named volume |
| Qdrant gRPC API | `localhost:6334` | Docker named volume |
| FastAPI | `localhost:8000` | Stateless container |
| Celery worker | Redis-backed queue | Stateless container |
| Celery scheduler | Redis-backed beat schedule | Stateless container |

The Qdrant image is pinned to `v1.19.1` so rebuilding the local stack does not
silently pull a different database release. Upgrade the tag deliberately and
verify the new image against the current vector-store adapter before adopting it.

PostgreSQL credentials are configured with `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`; keep those values aligned with `DATABASE_URL` in `.env`.
The default credentials are for local development only.

## Start services

Copy `.env.example` to `.env`, configure the provider and account credentials
needed by the features you plan to use, then start the application stack:

```bash
docker compose up -d --build
```

Compose starts PostgreSQL, Redis, and Qdrant first. A one-shot migration
container runs `alembic upgrade head`; the API, Celery worker, and Celery beat
scheduler start after the migration succeeds and their dependencies are healthy.
The API is available at `http://localhost:8000` and its health endpoint is
`/health`.

Host ports can be changed through the `FIKRAH_*_PORT` values in `.env` when a
port is already in use. Keep `DATABASE_URL`, `REDIS_URL`, and `QDRANT_URL`
aligned with those host ports; Compose overrides the service URLs inside the
application containers to use the internal service names.
