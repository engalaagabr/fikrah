# API and Worker in the Local Compose Stack

## Status

Implemented.

## Services

The development Compose stack includes PostgreSQL, Redis, Qdrant, a FastAPI
container, a Celery worker, a Celery beat scheduler, and a one-shot Alembic
migration container. API, worker, and scheduler images share the same Dockerfile
and dependencies; their commands and runtime roles remain separate.

The API binds to `127.0.0.1` on the configured `FIKRAH_API_PORT`. Supporting
services also bind only to loopback and support configurable host ports. Inside
Compose, application services connect over the Compose network using service
names and container ports. Host-side application connection URLs continue to
use the corresponding host ports.

## Startup ordering

PostgreSQL, Redis, and Qdrant must be healthy before application containers
start. The migration container applies all migrations and must complete
successfully before the API, worker, or scheduler starts. The API exposes the
existing `/health` liveness endpoint as its container health check.

## Local security

The Docker build excludes `.env`, Git data, virtual environments, and Python
caches. Runtime application services load credentials from the ignored local
`.env`; migrations receive only the PostgreSQL connection URL. Images run as a
non-root application user.

Celery beat keeps its local schedule file under `/tmp`; durable job state remains
in PostgreSQL, so the schedule file is not application data.

## Run

```bash
docker compose up -d --build
docker compose ps
```

The API is available at `http://localhost:8000`. Use
`docker compose logs -f api worker scheduler migrate` to inspect service startup
and job processing.
