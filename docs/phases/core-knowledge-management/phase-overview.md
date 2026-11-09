# Phase: Core Knowledge Management

## Goal

Give signed-in users a project container for organizing their personal notes and make project ownership boundaries explicit in the API.

## Scope

- Project list, creation, retrieval, rename, and deletion APIs.
- Protected `General` project behavior and per-user project isolation.
- Note storage and lifecycle APIs with user isolation, idempotent capture, processing intents, and deletion cleanup.
- Initial note analysis, including title generation, rewrite proposals, concepts, and Qdrant embeddings.
- Project-scoped semantic search and chat over project notes.
- Knowledge connections and graph retrieval remain separate features with their own contracts.

## Completion Criteria

- Project operations are authenticated and scoped to the current user.
- The General project is created for each new account and cannot be deleted.
- Project API contracts, migration dependencies, and tests are documented.
- Note and project deletion remove note connections and persist Qdrant cleanup requests atomically; Qdrant deletion is completed asynchronously by the worker feature.
- Semantic search is limited to the selected project and returns only current, completed note revisions that PostgreSQL verifies belong to the authenticated user.
- Project chat stores isolated conversation history, cites only authorized current note revisions, and clearly reports when project notes do not support an answer.
