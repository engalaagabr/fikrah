# Core Knowledge Management: Connections Increment

## Delivered Scope

- Generate note-to-note links after successful LLM processing when at least one extracted concept matches a completed note in the same user's project.
- Refresh outgoing links when a note is processed again; keep at most ten strongest candidates per processing run.
- Provide authenticated note-related and project-graph retrieval routes.
- Keep graph results within the authenticated user and selected project, and omit notes whose processing is not complete.

## Phase Relationship

This increment uses the existing `note_connections` table and note concepts, so it adds no database migration or external service. See [`docs/features/knowledge-connections/overview.md`](../../features/knowledge-connections/overview.md) for the contract and implementation details.

Project-scoped semantic search is tracked separately. Chat with project knowledge and project clustering remain outside this increment.
