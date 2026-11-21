# Layer-First Modular Architecture

## Purpose

FIKRAH is a modular monolith organized by technical layer. Each layer has one primary responsibility, and dependencies flow inward from HTTP and worker entry points toward application services and data or provider boundaries.

## Layer map

| Path | Responsibility |
| --- | --- |
| `app/main.py` | Create the FastAPI application, configure lifespan, and register routers. |
| `app/core/` | Shared settings and security primitives. |
| `app/api/deps.py` | Shared database/authentication dependencies and API-facing service providers. |
| `app/api/v1/` | Thin HTTP routers and API-to-application mapping, including `/health`. |
| `app/db/` | Declarative metadata and async/synchronous SQLAlchemy session factories. |
| `app/models/` | SQLAlchemy persistence models grouped by ownership: accounts, projects, notes, processing, connections, chat, and email delivery. |
| `app/contracts/` | Shared framework-independent commands, result values, and processing snapshots; contains no orchestration or persistence logic. |
| `app/schemas/` | Pydantic request and response schemas, grouped by feature. |
| `app/repositories/` | PostgreSQL reads/writes for API use cases and worker connection updates. API repositories flush; API services own commits. |
| `app/services/` | Application workflows and their service errors/ports. |
| `app/llm/` | LLM ports, prompts, use cases, factory, and provider adapters. |
| `app/rag/` | Embedding, Qdrant, candidate retrieval with PostgreSQL validation, and note processing/indexing orchestration. |
| `app/workers/` | Celery app configuration and task entry points. Existing note/vector task names retain their historical `app.worker.tasks.*` values; account-email delivery uses an explicit `app.workers.tasks.*` name. |
| `app/infrastructure/` | Composition roots and external integrations such as SMTP and Google identity. Worker-specific persistence adapters remain here because they own their existing `session.begin()` transaction boundaries. |
| `static/emails/` | HTML email templates. |
| `migrations/` | Alembic environment and versioned schema history; version files stay at the repository root. |

There is no shared logging configuration in the current application. Feature-specific service errors remain next to application services rather than introducing an unused global exception layer.

## Dependency direction

```text
HTTP request → API router → application service → repository → PostgreSQL
                                  │
                                  ├── LLM use case/provider
                                  └── RAG retriever/vector store

Celery task → worker composition root → note-processing service → repositories and RAG
```

Routers validate HTTP input, obtain the authenticated user and application-service instances through `app/api/deps.py`, call services, and map results/errors to HTTP responses. They do not import the infrastructure composition root directly or own SQL, provider SDK calls, or product workflows. `app/infrastructure/container.py` constructs the shared service instances; API providers expose them through FastAPI dependencies.

Application errors carry feature-specific failure codes and safe messages, plus retry timing where needed. HTTP status and header mappings live in the route layer; services do not select HTTP responses. The authentication dependency separately translates an invalid/revoked identity to its existing bearer challenge.

Application services own API workflow rules, user/project scoping, and transaction commits. API repositories execute database operations and flush when needed; they do not commit. Worker persistence remains a deliberate exception: its existing adapter methods use `session.begin()` so the worker’s atomic transaction boundaries remain unchanged.

Qdrant returns candidate note identifiers and indexed revisions. `app/rag/retriever.py` validates each candidate against PostgreSQL for the authenticated user, selected project, completed state, and current revision before returning it. PostgreSQL remains authoritative.

## Feature ownership

- Authentication routes and schemas live in `app/api/v1/auth.py` and `app/schemas/auth.py`; workflows/errors/ports live in `app/services/`, and shared commands/results in `app/contracts/`.
- Projects, notes, search, connections, and chat follow the same split: HTTP in `app/api/v1/`, schemas in `app/schemas/`, workflows in `app/services/`, and database access in `app/repositories/`.
- Persistence classes live in feature-specific model modules. `auth.py` owns account/authentication tables only; note/project/connection/processing tables are defined once in their respective modules. `app.models` is the canonical model catalog used to load Alembic metadata.
- `app/llm/prompts.py` and `app/llm/use_cases.py` own prompt composition and model-agnostic LLM workflows. Provider adapters only implement provider transport and structured response handling.
- Text and embedding factories return an owned client with `close()`. Consumers use `app/llm/lifecycle.py` to create/use/close per operation. Async consumers offload the entire ownership scope, so cancellation cannot close an in-flight synchronous SDK request. Prompt use cases borrow their argument; they do not own its lifetime.
- `app/rag/pipeline.py` coordinates note analysis and indexing; `app/rag/retriever.py` coordinates vector candidates and PostgreSQL verification.
- Services, RAG retrieval, and persistence depend on `app/contracts/` for shared values. The retriever does not import service implementation modules; persistence imports processing snapshots from the contract module, never from the pipeline. RAG protocols live in `app/rag/ports.py`.
- `app/workers/tasks.py` contains Celery task entry points. Provider and session construction lives in worker composition modules, not in route handlers.

## Rules for future changes

- Put HTTP concerns in `app/api/v1/`; keep route functions thin.
- Put request/response validation in `app/schemas/`; do not return ORM records as API contracts.
- Put business workflows and ownership rules in `app/services/`.
- Put API database access in `app/repositories/`; preserve SQL ordering and transaction boundaries when extracting existing code.
- Keep API service commits outside repositories. Preserve the worker persistence transaction boundaries unless a separately approved behavior-preserving change moves their ownership.
- Keep prompts out of provider adapters. Select providers through deployment configuration, never from client input.
- Treat Qdrant search results as untrusted candidates and validate them against PostgreSQL.
- Keep user identity sourced from the authenticated request context.
- Preserve public routes, payloads, headers, and status codes during structural changes.
- Keep Celery task registration names stable even when Python modules move.
- Put new feature documentation under `docs/features/<feature>/` and phase documentation under `docs/phases/<phase>/`, using a descriptive kebab-case document title.
