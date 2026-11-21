# Local Development Stack

## Purpose

Run the complete local backend stack: PostgreSQL, Redis, Qdrant, Mailpit, the
FastAPI application, a Celery worker, and a Celery beat scheduler. This stack is
for backend development; it does not define production deployment or expose
services beyond the local machine.

## Services

| Service | Local endpoint | Persistence |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | Docker named volume |
| Redis | `localhost:6379` | Docker named volume with AOF (`appendfsync everysec`) |
| Qdrant HTTP API | `localhost:6333` | Docker named volume |
| Qdrant gRPC API | `localhost:6334` | Docker named volume |
| Mailpit SMTP | `localhost:1025` | In-memory message capture |
| Mailpit web UI | `localhost:8025` | In-memory message capture |
| FastAPI | `localhost:8000` | Stateless container |
| Celery worker | Redis-backed queue | Stateless container |
| Celery scheduler | Redis-backed beat schedule | Stateless container |

The Qdrant image is pinned to `v1.19.1` so rebuilding the local stack does not
silently pull a different database release. Upgrade the tag deliberately and
verify the new image against the current vector-store adapter before adopting it.

PostgreSQL credentials are configured with `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`; keep those values aligned with `DATABASE_URL` in `.env`.
The default credentials are for local development only.

Runtime dependencies use `fastapi[standard-no-fastapi-cloud-cli]` to retain the
standard server tools without the unused cloud deployment CLI, as described in
the [FastAPI installation documentation](https://fastapi.tiangolo.com/#without-fastapi-cloud-cli).
`pydantic-settings` is declared directly because `app/core/config.py` imports it;
configuration must not depend on that package arriving transitively through a
deployment CLI. A fresh Python 3.12 Docker build is part of runtime verification.

## Start services

Copy `.env.example` to `.env`, configure the provider and account credentials
needed by the features you plan to use, then start the application stack:

```bash
docker compose up -d --build
```

Compose starts PostgreSQL, Redis, Qdrant, and Mailpit first. A one-shot migration
container runs `alembic upgrade head`; the API, Celery worker, and Celery beat
scheduler start after the migration succeeds and their dependencies are healthy.
The API is available at `http://localhost:8000` and its health endpoint is
`/health`. Account emails are captured by Mailpit and can be read at
`http://localhost:8025`. Compose routes both API delivery and durable email retries
from the Celery worker to `mailpit:1025` through one shared SMTP configuration.
Both senders wait for Mailpit to be healthy. Host SMTP credentials from `.env`
are overridden inside these two containers, so retries cannot accidentally use an
external mail server while initial delivery uses Mailpit.
Empty SMTP usernames/passwords are normalized to absent credentials by the email
adapter. Passing empty strings to the SMTP client would still request AUTH,
which Mailpit does not advertise by default.

Host ports can be changed through the `FIKRAH_*_PORT` values in `.env` when a
port is already in use. Keep `DATABASE_URL`, `REDIS_URL`, and `QDRANT_URL`
aligned with those host ports; Compose overrides the service URLs inside the
application containers to use the internal service names.

## Upgrade an existing development database

Use this repository's Compose file and project name consistently. An old running
API can still return `/health` successfully while its dependencies are stopped;
that endpoint is a liveness check, not a database or provider readiness check.

Before applying migrations, stop `api`, `worker`, and `scheduler`, start
`postgres`, `redis`, `qdrant`, and `mailpit`, and create a PostgreSQL backup with
`pg_dump -Fc`. Store the backup outside the repository with owner-only file
permissions. Keep existing named volumes; do not use `down -v` for an upgrade.

```bash
docker compose -p fikrah stop api worker scheduler
docker compose -p fikrah up -d postgres redis qdrant mailpit
docker compose -p fikrah build migrate api worker scheduler
docker compose -p fikrah run --rm migrate
docker compose -p fikrah up -d api worker scheduler
docker compose -p fikrah ps -a
```

The ownership migration aborts if existing notes or conversations reference a
project owned by a different user. Investigate such records instead of deleting
or reassigning them automatically. The session-family migration invalidates
legacy sessions; existing users must sign in again after this upgrade.

## Verify the running stack

- Check `/health`, `/openapi.json`, the migration revision, and Celery worker ping.
- Register a separate test account, inspect its verification and welcome emails in
  Mailpit, verify the account, and exercise password login and reset.
- Run `scripts/smoke_api.py` with that verified test account to check project,
  note, conversation, refresh, logout, and cleanup operations. It creates and
  deletes its own project; it does not delete the account.
- Use `scripts/test_api_endpoints.py` for individual interactive requests.
- Use `--with-llm` on the smoke script only when generation credentials **and**
  `GEMINI_API_KEY` for embeddings are configured. Without embeddings, successful
  liveness and CRUD checks do not establish working processing, search, or RAG.

Never print passwords, action links, API keys, or session tokens in a verification
report. Do not change `.env` or reuse another project's database/vector containers
to make a check pass.

## Verification on 2026-11-21

- Built all four application images with Python 3.12 and ran the existing database
  from revision `20261109_05` through `20261121_03` after taking a private backup.
- Verified PostgreSQL, Redis, Qdrant, Mailpit, API health, worker ping, task
  registration, dependency consistency (`pip check`), and both live ownership
  constraints. The scheduler dispatches jobs and email delivery tasks successfully.
- Verified registration, rejection of unverified login, activation, password
  reset, immediate rejection of the old access token, and General protection.
- Confirmed the worker recovered the original deferred verification and welcome
  emails on their second delivery attempt; password reset mail arrived directly.
- Passed 22 smoke checks without LLM calls and one interactive `/health` check.
  The worker was stopped during note CRUD, then restarted after those notes were
  deleted, to avoid paid generation retries with missing embedding credentials.
  Its vector cleanup task completed successfully afterward.
- Passed 174 automated tests with isolated PostgreSQL and Redis, Ruff, API startup,
  offline Alembic metadata/SQL generation, and Celery task registration.
- Removed the synthetic test account and its dependent data. Kept the pre-existing
  account, named volumes, and unrelated Compose projects intact.

**Not verified:** successful live note processing, semantic retrieval, and grounded
chat. `GEMINI_API_KEY` was absent, and the search endpoint returned the documented
`503` instead of claiming a successful result. No text-generation provider was
called during these checks. Add embedding credentials locally, recreate the API
and worker so they load them, and run the smoke script with `--with-llm` before
calling these features operational.
