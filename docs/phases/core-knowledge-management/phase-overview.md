# Phase: Core Knowledge Management

## Goal

Give signed-in users a project container for organizing their personal notes and make project ownership boundaries explicit in the API.

## Scope

- Project list, creation, retrieval, rename, and deletion APIs.
- Protected `General` project behavior and per-user project isolation.
- Note storage and lifecycle APIs with user isolation, idempotent capture, processing intents, and deletion cleanup.
- Initial note analysis, including title generation, rewrite proposals, concepts, and Qdrant embeddings.
- Knowledge connections, project clusters, graph retrieval, and chat remain later features with their own approved contracts. Project-scoped semantic search is implemented in its feature document.

## Completion Criteria

- Project operations are authenticated and scoped to the current user.
- The General project is created for each new account and cannot be deleted.
- Project API contracts, migration dependencies, and tests are documented.
- Note and project deletion remove note connections and persist Qdrant cleanup requests atomically; Qdrant deletion is completed asynchronously by the worker feature.
- Semantic search is limited to the selected project and returns only current, completed note revisions that PostgreSQL verifies belong to the authenticated user.
