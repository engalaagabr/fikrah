# Phase: Core Knowledge Management

## Goal

Give signed-in users a project container for organizing their personal notes and make project ownership boundaries explicit in the API.

## Scope

- Project list, creation, retrieval, rename, and deletion APIs.
- Protected `General` project behavior and per-user project isolation.
- Note storage and lifecycle APIs in a later feature.
- AI processing, knowledge connections, vectors, search, and chat after their persistence and processing contracts are implemented.

## Completion Criteria

- Project operations are authenticated and scoped to the current user.
- The General project is created for each new account and cannot be deleted.
- Project API contracts, migration dependencies, and tests are documented.
- Note deletion and external vector cleanup are implemented with their corresponding note data feature before those records are introduced.
