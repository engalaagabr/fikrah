# Local Development Stack

## Purpose

Provide local PostgreSQL, Redis, and Qdrant services matching the connection
defaults in `.env.example`. This stack is for backend development; it does not
define production deployment or expose the services beyond the local machine.

## Services

| Service | Local endpoint | Persistence |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | Docker named volume |
| Redis | `localhost:6379` | Docker named volume with AOF (`appendfsync everysec`) |
| Qdrant HTTP API | `localhost:6333` | Docker named volume |
| Qdrant gRPC API | `localhost:6334` | Docker named volume |

PostgreSQL credentials are configured with `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`; keep those values aligned with `DATABASE_URL` in `.env`.
The default credentials are for local development only.

## Start services

Copy `.env.example` to `.env`, then start the supporting services:

```bash
docker compose up -d postgres redis qdrant
```

After the services are ready, run migrations and start the API and worker from
the project virtual environment. This feature does not start containers or apply
migrations automatically.
