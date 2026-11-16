# Project Template Guide

This guide explains where code belongs in a layer-first FastAPI backend. It is written to be reusable when starting another modular monolith.

## Folder responsibilities

| Folder | Put this here |
| --- | --- |
| `app/core/` | Application-wide settings, security primitives, and truly shared infrastructure policy. |
| `app/api/` | FastAPI dependencies and versioned route modules. |
| `app/db/` | SQLAlchemy base metadata and database session/engine setup. |
| `app/models/` | ORM table mappings. |
| `app/schemas/` | Request and response validation models. |
| `app/repositories/` | Database queries and persistence operations. |
| `app/services/` | Use cases, business rules, application contracts, and application errors. |
| `app/llm/` | Model-independent prompts/use cases, provider interfaces, provider adapters, and provider factory. |
| `app/rag/` | Embeddings, vector-store adapter, retrieval and verification, and indexing pipelines. |
| `app/workers/` | Queue app configuration and thin task entry points. |
| `app/infrastructure/` | Composition roots and external-system adapters that do not belong to a product use case. |
| `static/` | Static files consumed at runtime, such as HTML email templates. |
| `migrations/` | Alembic environment and versioned database schema history. |
| `tests/` | Unit and integration tests organized around the behavior under test. |

## Where do I put X?

- **A URL handler, status code, or HTTP header?** `app/api/v1/<resource>.py`.
- **A request body or response shape?** `app/schemas/<resource>.py`.
- **A rule such as ownership, lifecycle, or a multi-step workflow?** `app/services/<resource>_service.py`.
- **A SQL query or persistence operation?** `app/repositories/<resource>.py`.
- **A table mapping?** `app/models/`.
- **A setting, password hash, or token helper used across the app?** `app/core/`.
- **A vendor SDK call?** An adapter under `app/infrastructure/`, `app/llm/providers/`, or `app/rag/`, according to what it integrates with.
- **A prompt or model-independent structured LLM workflow?** `app/llm/`.
- **A vector search, embedding, or indexing operation?** `app/rag/`.
- **A background queue entry point?** `app/workers/`; delegate its work to an application service.
- **A database schema change?** A new Alembic revision under `migrations/versions/`, after approval.

## Request and worker flows

An HTTP request follows:

```text
Router → Service → Repository → Database
   │         ├── LLM use case/provider
   │         └── RAG retrieval/vector store
   └── Schema validation and response mapping
```

The router handles HTTP input/output and obtains the caller identity from shared API dependencies. The service applies application rules and owns the API transaction. The repository performs persistence and flushes without committing.

A background task follows:

```text
Celery task → Worker composition → Application processing service → Repository/RAG adapters
```

Keep task functions small. They should parse task arguments, call the processing workflow, and handle task-level retry/acknowledgement policy.

For retrieval-augmented generation, treat vector-store hits as candidates. Validate ownership, scope, status, and indexed revision against the authoritative relational database before returning them to a caller.

## Adding a feature

1. Define the feature’s request and response schemas in `app/schemas/`.
2. Add application result/command contracts and the use case in `app/services/`.
3. Put database queries in `app/repositories/`; keep commits in the application workflow.
4. Add a thin router in `app/api/v1/` and register it in `app/main.py`.
5. Add focused unit/integration tests for behavior, authorization, failure cases, and public status codes.
6. If background processing is needed, add a thin task under `app/workers/` and preserve stable registered task names.
7. Update feature and architecture documentation, then run the project’s full test, lint, startup, migration-load, and worker-registration checks.

Keep dependencies pointed inward: API and worker entry points can call application workflows; services can depend on repository and provider interfaces; lower-level adapters should not import routers or choose product behavior.
