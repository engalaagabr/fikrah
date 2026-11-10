# Mobile API Surface

**Status: Implemented.** This document records the current mobile-facing API contract for authentication, projects, notes, processing, refinement, knowledge connections, graph retrieval, semantic search, and project chat. The modular architecture is documented in [`docs/architecture/layered-modular-architecture.md`](../../architecture/layered-modular-architecture.md).

## Contract-wide rules

- All endpoints except account registration, login, Google sign-in, token refresh, email verification, and password-reset requests/completion require an authenticated user.
- Every database and vector lookup is scoped to the authenticated user's data. The client does not choose or submit an owner ID.
- Note content sent to the Backend is plain text. The mobile app extracts voice and PDF text locally, and original PDFs remain on-device. There is no file upload or server-side extraction endpoint in this proposal.
- Project-scoped operations verify that the selected project belongs to the authenticated user. `General` is the default project and cannot be deleted.
- Deleting a project removes its notes; deleting a note or project also removes associated knowledge links and schedules durable Qdrant cleanup.
- Suggested refinement text is a proposal. Accepting replaces the current note text permanently; rejecting removes the proposal. A user can request another proposal.
- Responses use backend-generated stable resource IDs and explicit processing state. Lists are unpaginated in the initial version; errors use FastAPI's standard `detail` response and timestamps are UTC.

## Authentication and account — Implemented

The authoritative paths, request/response schemas, and mobile workflow are documented in [`docs/features/authentication/overview.md`](../authentication/overview.md). Implemented routes include registration, email verification and resend, login, Google sign-in, password reset request and completion, token refresh, logout, and `GET /v1/auth/me`.

Account deletion, concurrent-session behavior, and profile editing remain out of scope.

## Projects — Implemented

Project operations are implemented with per-user ownership checks. `General` is protected from deletion.

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/projects` | List a user's projects and identify the protected default project. | On app startup and after project changes. | Optional pagination/sort parameters, if needed. | Projects with ID, name, protected/default flags, and optionally note counts. |
| `POST /v1/projects` | Create a project so the user can organize notes outside `General`. | When the user creates a project. | Project name. | Created project. |
| `GET /v1/projects/{project_id}` | Retrieve project details for a project view. | When opening or refreshing a project. | Project ID in the path. | Project details and any agreed summary metadata. |
| `PATCH /v1/projects/{project_id}` | Rename a project. | When the user saves a project-name edit. | Updated project name. | Updated project. |
| `DELETE /v1/projects/{project_id}` | Delete a project and its notes, links, and associated vectors. | When the user confirms project deletion. | Project ID in the path. | `204`; vector cleanup is queued durably. The protected `General` project is rejected. |

## Notes and processing — Implemented

List pagination is deferred. Note responses also contain `concepts`, an optional `refinement_proposal`, and `processing_generation` for safe processing/proposal actions.

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/projects/{project_id}/notes` | Save a note and enqueue Backend-owned LLM processing. | After the user saves text or locally extracted audio/PDF text. | Plain text, optional user title, and an `Idempotency-Key` header (1–128 characters). Reuse the same key for retries of the same capture. No file. | `201` with Backend-generated note ID, project ID, optional title, text, revision, `queued` state, and timestamps. Reusing a key with a different request returns `409`; replaying a creation whose note has since been deleted returns `410`. |
| `GET /v1/projects/{project_id}/notes` | List notes for a project. | When opening or refreshing a project. | Project ID in the path; no pagination initially. | Full note records ordered by most recently updated. |
| `GET /v1/notes/{note_id}` | Fetch the latest note and its processing state for polling. | When opening a note and periodically until its processing state is terminal. | Note ID in the path. | Current text/title, revision, processing generation, concepts, optional refinement proposal, state (`queued`, `processing`, `completed`, `failed`), and timestamps. |
| `PATCH /v1/notes/{note_id}` | Save user edits and enqueue processing for the new revision. | Whenever the user saves a note edit. | Changed text and/or title; at least one field. | Updated note and `queued` state. Old revision results must not overwrite the current revision. |
| `DELETE /v1/notes/{note_id}` | Delete a note and its connections and associated vector. | When the user confirms note deletion. | Note ID in the path. | Deletion result; vector cleanup may finish asynchronously. |
| `POST /v1/notes/{note_id}/processing-retries` | Retry LLM processing while preserving the note. | When the user requests reprocessing or a previous attempt failed. | Note ID in the path; no retry reason. | `202` with the current note and `queued` state. |

LLM generates a title during processing only when the user did not supply one. While title generation is pending, mobile can show `Processing…` as a UI-only placeholder; the value is not persisted as the note title. Mobile polls the note response for processing status; the interval/backoff remains for mobile integration guidance.

## Refinement proposals — Implemented

| Endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/notes/{note_id}/refinement-regenerations` | Generate a new wording proposal after the user rejected the previous one or requests another version. | When the user asks for another rewrite. | `expected_processing_generation` from the displayed note. | `202` with the proposal cleared and a new queued processing generation. |
| `PATCH /v1/notes/{note_id}/refinement-proposal` | Save the user's manually edited rewrite before accepting it. | Whenever the user saves edits to a displayed proposal. | `expected_processing_generation` and nonblank edited `refinement_proposal`. | `200` with the edited proposal, unchanged original note content, and incremented processing generation. |
| `POST /v1/notes/{note_id}/refinement-acceptance` | Apply the currently displayed proposal by replacing the note text permanently and starting processing for the new text. | When the user accepts the proposal. | `expected_processing_generation` from the displayed note. | `200` with updated content, cleared proposal, and new revision/generation in `queued` state. |
| `POST /v1/notes/{note_id}/refinement-rejections` | Reject and remove the displayed proposal. | When the user rejects it. | JSON body with `expected_processing_generation` from the displayed note. | `200` with the proposal removed and unchanged note content. |

The proposal must use the same language as the original note. A result produced for an older note revision or processing generation must not overwrite a newer result. Editing changes only the proposal; the original note stays intact until acceptance. Accepting replaces the note text and starts processing automatically. Rejection clears the proposal while retaining the original note text. Regeneration clears the current proposal, then asynchronously generates another proposal for the unchanged note text. Each action includes the `processing_generation` returned in the note representation; stale actions return `409` rather than acting on a proposal the user may not have seen. See [`docs/features/note-refinement-actions/overview.md`](../note-refinement-actions/overview.md).

## Knowledge connections and graph — Implemented

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/notes/{note_id}/connections` | Retrieve notes connected to the current note for a related-notes view. | When opening a note's connections panel. | Note ID in the path. | Related note ID, title, shared concepts, and update timestamp; limited to the authenticated user's project. |
| `GET /v1/projects/{project_id}/knowledge-graph` | Retrieve graph nodes and edges for project visualization. | When opening or refreshing the project graph. | Project ID in the path. | All completed project note nodes and shared-concept edges; no pagination or viewport filtering initially. |

Connections are generated after processing when at least one normalized concept matches a completed note in the same user-owned project. The worker stores up to ten strongest directed suggestions per processing run; retrieval treats links as undirected. Individual connection create/edit/delete operations are not exposed. See [`docs/features/knowledge-connections/overview.md`](../knowledge-connections/overview.md).

## Semantic search — Implemented

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/projects/{project_id}/search` | Find relevant notes in the selected project by meaning and context instead of exact keywords. | When the user submits a search query while a project is selected. | Project ID in the path, non-blank query text (max 4,000 characters), and optional `limit` (default 10, range 1–50). | Ordered matching notes with ID, title, content, relevance score, and update timestamp; empty array when no current completed vectors match. PostgreSQL validates user/project ownership, completion, and indexed revision before returning any result. |

## Chat with project knowledge — Implemented

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/projects/{project_id}/conversations` | List a user's conversations in a project. | When opening or refreshing project chat history. | Project ID; no pagination initially. | Conversation IDs, optional titles, and timestamps ordered by most recently updated. |
| `POST /v1/projects/{project_id}/conversations` | Start a conversation scoped to the selected project. | When the user starts a new chat. | Optional user-provided title. If absent, the first question becomes the title, limited to 120 characters. | Created project-scoped conversation; title is null until its first message if no title was supplied. |
| `GET /v1/conversations/{conversation_id}` | Load conversation history. | When opening a prior conversation. | Conversation ID; no pagination initially. | Full ordered messages with roles, content, support status, cited note IDs/titles, and timestamps. |
| `POST /v1/conversations/{conversation_id}/messages` | Ask a question and receive an answer grounded in the selected project's notes. | When the user sends a chat message. | Non-blank question text up to 4,000 characters. | Complete user and assistant messages in one response, with `supported` status and validated source note references. When notes do not support an answer, the assistant clearly says so in the question's language and returns no sources. |
| `DELETE /v1/conversations/{conversation_id}` | Delete a conversation and its chat history. | When the user deletes a conversation. | Conversation ID. | `204`; project deletion also removes its conversations, and note deletion removes citation records for that note. |

Conversation ownership, note-context scoping, and chat history are isolated per user. Retrieval uses up to eight current, completed note vectors from the selected project, verified against PostgreSQL. The latest twelve messages provide follow-up context but are not evidence. Answers use the same language as the question and do not stream. See [`docs/features/project-knowledge-chat/overview.md`](../project-knowledge-chat/overview.md).

## Deferred product decisions

Language-specific handling for mixed-language chats, list pagination, and production deployment capacity remain deferred. If the model returns an answer whose citations cannot be validated, the Backend requests a refusal in the question's language without supplying note evidence; it does not expose the unvalidated answer. Current queue recovery behavior is documented in [`docs/features/celery-recovery-config/overview.md`](../celery-recovery-config/overview.md).
