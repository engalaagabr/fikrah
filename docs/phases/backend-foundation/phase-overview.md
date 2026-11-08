# Phase: Backend Foundation

## Goal

Create the smallest runnable foundation for the FIKRAH Backend using the user-selected FastAPI framework.

## Scope

- Establish the Python/FastAPI application entry point.
- Provide a basic operational health endpoint.
- PostgreSQL and Qdrant have been selected. PostgreSQL is the source of truth for application records; Qdrant stores embeddings and retrieval metadata.
- Cross-store synchronization and recovery behavior remain open until designed.
- Keep authentication-provider and AI-provider decisions open until product and architecture requirements are discussed.

## Not Included Yet

- Authentication or account management.
- Persistence or database integration.
- AI provider integration or note-processing workflows.
- Product endpoints for notes, projects, search, graph, or chat.

## Completion Criteria

- The API application can be started locally.
- The health endpoint returns a simple status response.
- Feature and phase documentation are maintained in English by default.
