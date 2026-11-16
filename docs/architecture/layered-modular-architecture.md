# Layered Modular Backend Architecture

## Status

Implemented as a modular monolith. Each product capability is a module; modules use a presentation layer for HTTP, an application layer for use cases, and repositories or infrastructure adapters for persistence and external systems. PostgreSQL ORM models currently serve as persistence records shared by these layers.

## Dependency direction

```text
FastAPI routes  →  feature application services  →  feature contracts / LLM ports
                          ↓                               ↑
                  feature repositories        infrastructure adapters
                          ↓                    (Qdrant, Redis/Celery, SMTP, LLM)
                   PostgreSQL
```

HTTP handlers translate HTTP input/output and delegate to application services; they do not own business workflows. Application services enforce ownership, lifecycle, and orchestration rules, and report expected failures with application-level errors that routes translate into HTTP responses. Feature repositories own SQLAlchemy reads and writes and flush pending changes; application services own transaction boundaries and commits. `app/infrastructure/persistence/` owns shared async and worker session lifecycle plus durable worker persistence. `app/core/config.py` centralizes environment settings, and `app/core/security.py` contains password and token helpers. `app/infrastructure/container.py` is the API composition root; `app/infrastructure/worker_container.py` composes the Celery processing use case separately for the worker runtime.

## Module map

| Module | HTTP | Application | Infrastructure boundary |
|---|---|---|---|
| Authentication | `app/auth/routes.py` | `app/auth/service.py`, `app/services/contracts/auth.py`, `app/schemas/auth.py` | `app/auth/repository.py`; SMTP and Google adapters under `app/infrastructure/` |
| Projects | `app/projects/routes.py` | `app/projects/service.py`, shared result contracts and schemas | `app/projects/repository.py` |
| Notes | `app/notes/routes.py` | `app/notes/service.py`, shared commands/results and schemas; `app/rag/pipeline.py` | `app/notes/repository.py`; worker processing/outbox adapters under `app/infrastructure/persistence/` |
| Search | `app/search/routes.py` | `app/search/service.py`, shared result contracts and schemas | `app/search/repository.py`; `app/rag/embeddings.py` and `app/rag/vector_store.py` |
| Connections | `app/connections/routes.py` | `app/connections/service.py`, shared result contracts and schemas | `app/connections/repository.py`; worker link persistence in `app/connections/persistence.py` |
| Chat | `app/chat/routes.py` | `app/chat/service.py`, shared commands/results and schemas | `app/chat/repository.py`; search use case and configured text generator |
| LLM | — | `app/llm/contracts.py`, `ports.py`, `prompts.py`, and `use_cases.py` | `app/llm/providers/` adapters and `app/llm/factory.py` |
| Worker | — | Celery task entry points in `app/worker/tasks.py` | `app/infrastructure/persistence/worker_database.py`, worker repositories, Qdrant, Celery/Redis |

## LLM boundaries

`app/llm/contracts.py` and `ports.py` define shared results and the `StructuredTextGenerator` boundary. `app/llm/prompts.py` and `use_cases.py` own product prompts and chat workflows; `app/rag/pipeline.py` orchestrates note analysis and indexing through injected generator, embedding, persistence, and vector-store ports. Provider adapters under `app/llm/providers/` accept structured generation requests and contain provider transport and response validation; the shared OpenAI-compatible transport is implemented once. `LLMProviderFactory` in `app/llm/factory.py` constructs adapters from deployment configuration; request payloads cannot select a provider or model. Gemini remains the embedding adapter.

## Request and processing flow

1. A route validates the request with a feature schema and passes the authenticated user ID to its application service.
2. The application service applies ownership and product rules, persists the change, and schedules durable work where required.
3. Celery task entry points delegate to `NoteProcessingService`; its persistence adapter coordinates revision checks and database transactions, while the Qdrant adapter owns vector operations.
4. Search retrieves candidate vector IDs from Qdrant and validates ownership, project, completion state, and revision in PostgreSQL before returning notes.

## Rules for future changes

- Keep route modules thin; do not add SQL queries, provider SDK calls, or product decisions to route handlers.
- Keep prompts and response contracts out of provider adapter modules.
- Keep external SDK calls inside adapters; keep environment configuration in `app/core/config.py`; wire adapters to use cases in the composition root.
- Keep each feature's request/response schemas and use cases inside that feature module.
- Keep Celery task functions as transport entry points; put note-processing orchestration in the application service and database/vector operations behind their adapters.
- Let application services own transaction boundaries and commits. Repositories execute persistence operations and flush when required, but never commit independently.
- Pass the authenticated user ID from the API boundary; never accept an owner ID from a client request.
- Keep PostgreSQL authoritative for user-owned records. Treat Qdrant results as candidates that must be verified against PostgreSQL.
- Add cross-module dependencies through application-facing contracts/use cases, not by importing another module's route handlers.
- Name feature and phase documentation files after their document title, using lowercase kebab-case: `docs/features/<feature>/<document-title>.md` and `docs/phases/<phase>/<document-title>.md`. Keep each document inside its feature or phase directory and update links when a filename changes.

## Known migration boundary

SQLAlchemy ORM records are shared between services and repositories, but service modules no longer contain SQL statements. Repositories stay feature-scoped and own persistence operations; avoid introducing wrapper repositories that do not provide a meaningful boundary.
