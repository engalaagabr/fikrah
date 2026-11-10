# Layered Modular Backend Architecture

## Status

Implemented as a modular monolith. Each product capability is a module; modules use a presentation layer for HTTP, an application layer for use cases, and infrastructure adapters for external systems. PostgreSQL ORM models currently serve as persistence records shared by these layers.

## Dependency direction

```text
FastAPI routes  →  feature application services  →  feature contracts / LLM ports
                                              ↑
Infrastructure adapters (PostgreSQL, Qdrant, Redis/Celery, SMTP, LLM providers)
```

Dependencies point inward at contracts. HTTP handlers translate HTTP input/output and delegate to application services through feature contracts; they do not own business workflows. Application services enforce ownership, lifecycle, and orchestration rules, and report expected failures with application-level errors that routes translate into HTTP responses. Infrastructure contains provider SDKs, external-service calls, configuration, and durable queue/vector-store integration. `app/infrastructure/container.py` is the API composition root; `app/infrastructure/worker_container.py` composes the Celery processing use case separately for the worker runtime.

## Module map

| Module | HTTP | Application | Infrastructure boundary |
|---|---|---|---|
| Authentication | `app/auth/routes.py` | `app/auth/service.py`, schemas, shared auth dependencies, integration errors in `app/auth/ports.py` | SMTP and Google identity adapters under `app/infrastructure/`, wired through `app/infrastructure/container.py`; PostgreSQL token/session records |
| Projects | `app/projects/routes.py` | `ProjectService`, result contracts in `app/projects/contracts.py` | `ProjectRepository` and PostgreSQL |
| Notes | `app/notes/routes.py` | `NoteService`, `NoteProcessingService`, commands in `app/notes/contracts.py` | PostgreSQL sessions, worker processing repository, processing-job outbox, Celery worker |
| Search | `app/search/routes.py` | `SemanticSearchService`, result contracts in `app/search/contracts.py` | Gemini embeddings and Qdrant adapter |
| Connections | `app/connections/routes.py` | `KnowledgeConnectionService`, result contracts in `app/connections/contracts.py` | PostgreSQL read/write adapters in `app/connections/` and `app/infrastructure/persistence/` |
| Chat | `app/chat/routes.py` | `ChatService`, commands and results in `app/chat/contracts.py` | Search use case, configured text-model adapter, PostgreSQL history |
| LLM | — | result contracts, `StructuredTextGenerator` port, note/chat use cases, prompt definitions | `app/infrastructure/llm/` provider adapters and factory |
| Worker | — | Celery task entry points in `app/worker/tasks.py` | Sync PostgreSQL sessions, Qdrant vector-store adapter, Celery/Redis |

## LLM boundaries

`app/llm/contracts.py` and `ports.py` define shared results and the `StructuredTextGenerator` boundary. `app/llm/prompts.py` and `use_cases.py` own product prompts and chat workflows; `app/notes/processing.py` orchestrates note analysis and indexing through injected generator, embedding, persistence, and vector-store ports. Provider adapters under `app/infrastructure/llm/providers/` accept structured generation requests and contain only provider transport and response validation; the shared OpenAI-compatible transport is implemented once. `LLMProviderFactory` in `app/infrastructure/llm/factory.py` constructs adapters from deployment configuration; request payloads cannot select a provider or model. Gemini remains the embedding adapter.

## Request and processing flow

1. A route validates the request with a feature schema and passes the authenticated user ID to its application service.
2. The application service applies ownership and product rules, persists the change, and schedules durable work where required.
3. Celery task entry points delegate to `NoteProcessingService`; its persistence adapter coordinates revision checks and database transactions, while the Qdrant adapter owns vector operations.
4. Search retrieves candidate vector IDs from Qdrant and validates ownership, project, completion state, and revision in PostgreSQL before returning notes.

## Rules for future changes

- Keep route modules thin; do not add SQL queries, provider SDK calls, or product decisions to route handlers.
- Keep prompts and response contracts out of provider adapter modules.
- Keep external SDKs and service-specific configuration inside `app/infrastructure/`; wire adapters to use cases in the composition root.
- Keep each feature's request/response schemas and use cases inside that feature module.
- Keep Celery task functions as transport entry points; put note-processing orchestration in the application service and database/vector operations behind their adapters.
- Let application services own transaction boundaries. Repositories flush changes but do not commit independently.
- Pass the authenticated user ID from the API boundary; never accept an owner ID from a client request.
- Keep PostgreSQL authoritative for user-owned records. Treat Qdrant results as candidates that must be verified against PostgreSQL.
- Add cross-module dependencies through application-facing contracts/use cases, not by importing another module's route handlers.
- Preserve feature docs at `docs/features/<feature>/DOC.md` (or the feature's existing overview file) and phase docs at `docs/phases/<phase>/DOC.md` (or existing phase overview) when making future changes.

## Known migration boundary

The current implementation uses SQLAlchemy ORM records in several application services. This keeps the initial product implementation direct and transactional, but means persistence is not yet abstracted behind a repository in every module. New external integrations must still remain behind infrastructure adapters; additional repositories should be introduced when they provide a clear boundary or testability benefit rather than as boilerplate wrappers.
