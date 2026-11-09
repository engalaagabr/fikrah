# Layered Modular Backend Architecture

## Status

Implemented as a modular monolith. Each product capability is a module; modules use a presentation layer for HTTP, an application layer for use cases, and infrastructure adapters for external systems. PostgreSQL ORM models currently serve as persistence records shared by these layers.

## Dependency direction

```text
FastAPI routes  →  feature application services  →  feature contracts / AI ports
                                              ↑
Infrastructure adapters (PostgreSQL, Qdrant, Redis/Celery, SMTP, AI providers)
```

Dependencies point inward at contracts. HTTP handlers translate HTTP input/output and delegate to application services; they do not own business workflows. Application services enforce ownership, lifecycle, and orchestration rules, and report expected failures with application-level errors that routes translate into HTTP responses. Infrastructure contains provider SDKs, external-service calls, configuration, and durable queue/vector-store integration.

## Module map

| Module | HTTP | Application | Infrastructure boundary |
|---|---|---|---|
| Authentication | `app/auth/routes.py` | `app/auth/service.py`, schemas, shared auth dependencies | SMTP and Google identity adapters under `app/infrastructure/`, PostgreSQL token/session records |
| Projects | `app/projects/routes.py` | `ProjectService` | `ProjectRepository` and PostgreSQL |
| Notes | `app/notes/routes.py` | `NoteService` | PostgreSQL, processing-job outbox, Celery worker |
| Search | `app/search/routes.py` | `SemanticSearchService` | Gemini embeddings and Qdrant adapter |
| Connections | `app/connections/routes.py` | `KnowledgeConnectionService` | PostgreSQL connection records |
| Chat | `app/chat/routes.py` | `ChatService` | Search use case, configured text-model adapter, PostgreSQL history |
| AI | — | contracts, provider ports, prompt definitions | `app/infrastructure/ai/` adapters and provider factory |
| Worker | — | asynchronous processing entry points | Celery/Redis, PostgreSQL, AI and Qdrant adapters |

## AI boundaries

`app/ai/contracts.py`, `ports.py`, and `prompts.py` define the application-facing AI data and behavior. Prompts are authored outside provider adapters. `app/infrastructure/ai/` translates those contracts to Gemini, DeepSeek, or OpenRouter SDK/API formats. `AIProviderFactory` is infrastructure composition and reads deployment configuration; request payloads cannot select a provider or model. Gemini remains the embedding adapter.

## Request and processing flow

1. A route validates the request with a feature schema and passes the authenticated user ID to its application service.
2. The application service applies ownership and product rules, persists the change, and schedules durable work where required.
3. Celery workers load the persisted processing job, call application-facing AI contracts through infrastructure adapters, then save results and vectors.
4. Search retrieves candidate vector IDs from Qdrant and validates ownership, project, completion state, and revision in PostgreSQL before returning notes.

## Rules for future changes

- Keep route modules thin; do not add SQL queries, provider SDK calls, or product decisions to route handlers.
- Keep prompts and response contracts out of provider adapter modules.
- Keep external SDKs and service-specific configuration inside `app/infrastructure/`.
- Keep each feature's request/response schemas and use cases inside that feature module.
- Pass the authenticated user ID from the API boundary; never accept an owner ID from a client request.
- Keep PostgreSQL authoritative for user-owned records. Treat Qdrant results as candidates that must be verified against PostgreSQL.
- Add cross-module dependencies through application-facing contracts/use cases, not by importing another module's route handlers.
- Preserve feature docs at `docs/features/<feature>/DOC.md` (or the feature's existing overview file) and phase docs at `docs/phases/<phase>/DOC.md` (or existing phase overview) when making future changes.

## Known migration boundary

The current implementation uses SQLAlchemy ORM records in several application services. This keeps the initial product implementation direct and transactional, but means persistence is not yet abstracted behind a repository in every module. New external integrations must still remain behind infrastructure adapters; additional repositories should be introduced when they provide a clear boundary or testability benefit rather than as boilerplate wrappers.
