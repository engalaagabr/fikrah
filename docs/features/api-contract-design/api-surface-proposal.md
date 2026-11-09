# Mobile API Surface and Remaining Proposals

**Status: Partial.** Authentication is implemented and documented in `docs/features/authentication/overview.md`. The project routes below are approved and implemented. Remaining paths are proposals; their product behavior and detailed contracts must be approved before implementation.

## Contract-wide rules

- All endpoints except account registration, login, Google sign-in, token refresh, email verification, and password-reset requests/completion require an authenticated user.
- Every database and vector lookup is scoped to the authenticated user's data. The client does not choose or submit an owner ID.
- Note content sent to the Backend is plain text. The mobile app extracts voice and PDF text locally, and original PDFs remain on-device. There is no file upload or server-side extraction endpoint in this proposal.
- Project-scoped operations verify that the selected project belongs to the authenticated user. `General` is the default project and cannot be deleted.
- Deleting a project removes its notes; deleting a note or project also removes associated knowledge links and schedules durable Qdrant cleanup.
- Suggested refinement text is a proposal. Accepting replaces the current note text permanently; rejecting removes the proposal. A user can request another proposal.
- Responses should use stable resource IDs and explicit processing state. Exact ID generation, error format, pagination, and timestamp conventions remain open.

## Authentication and account — Implemented

The authoritative paths, request/response schemas, and mobile workflow are documented in [`docs/features/authentication/overview.md`](../authentication/overview.md). Implemented routes include registration, email verification and resend, login, Google sign-in, password reset request and completion, token refresh, logout, and `GET /v1/auth/me`.

Account deletion, concurrent-session behavior, and profile editing remain out of scope.

## Projects — Contract Accepted

The user approved the project routes below for implementation. The rest of this file remains a proposal until approved separately.

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/projects` | List a user's projects and identify the protected default project. | On app startup and after project changes. | Optional pagination/sort parameters, if needed. | Projects with ID, name, protected/default flags, and optionally note counts. |
| `POST /v1/projects` | Create a project so the user can organize notes outside `General`. | When the user creates a project. | Project name. | Created project. |
| `GET /v1/projects/{project_id}` | Retrieve project details for a project view. | When opening or refreshing a project. | Project ID in the path. | Project details and any agreed summary metadata. |
| `PATCH /v1/projects/{project_id}` | Rename a project. | When the user saves a project-name edit. | Updated project name. | Updated project. |
| `DELETE /v1/projects/{project_id}` | Delete a project and its notes, links, and associated vectors. | When the user confirms project deletion. | Project ID in the path. | Deletion result. The response's treatment of asynchronous vector cleanup is undecided. The protected `General` project must be rejected. |

## Notes and processing

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/projects/{project_id}/notes` | Save a note and start Backend-owned AI processing. | After the user saves text or locally extracted audio/PDF text. | Plain text, optional user title, and an `Idempotency-Key` header. Mobile reuses the same key when retrying the same request after a timeout. No file. | Backend-generated note ID, selected project ID, current title if supplied, processing state, and creation/update times. |
| `GET /v1/projects/{project_id}/notes` | List notes for a project. | When opening or refreshing a project. | Pagination and filters (open). | Notes with IDs, titles, processing states, and list-preview fields to be agreed. |
| `GET /v1/notes/{note_id}` | Fetch the latest note and AI processing result, including its processing state for polling. | When opening a note and periodically until its processing state is terminal. | Note ID in the path. | Current text/title, processing state, concepts, cluster, refinement proposal if any, connections or their IDs, and timestamps. Exact shape is open. |
| `PATCH /v1/notes/{note_id}` | Save user edits to note text or title and start a fresh processing job. | Whenever the user saves an edit to a note. | Changed text and/or title. | Updated note and new processing state. Results from earlier note versions must not overwrite this version. |
| `DELETE /v1/notes/{note_id}` | Delete a note and its connections and associated vector. | When the user confirms note deletion. | Note ID in the path. | Deletion result; vector cleanup may finish asynchronously. |
| `POST /v1/notes/{note_id}/processing-retries` | Retry AI processing while preserving the note. | When the user requests reprocessing or a previous attempt failed. | Note ID in the path; optional retry reason is not required by current product behavior. | Accepted retry state/job reference and current note processing state. |

AI generates a title during processing only when the user did not supply one. While title generation is pending, mobile can show `Processing…` as a UI-only placeholder; the value is not persisted as the note title. Mobile polls the note response for processing status; the exact state values and polling interval/backoff remain to be designed.

## Refinement proposals

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/notes/{note_id}/refinement-regenerations` | Generate a new wording proposal after the user rejected the previous one or requests another version. | When the user asks for another rewrite. | Note ID; optionally the unchanged source-text version to prevent applying a stale result. | Accepted processing state and later a proposal in the note response. |
| `POST /v1/notes/{note_id}/refinement-acceptance` | Apply the currently displayed proposal by replacing the note text permanently and starting processing for the new text. | When the user accepts the proposal. | Proposal ID or note revision to prevent accepting a stale proposal (exact concurrency contract open). | Updated note text, cleared proposal, and new processing state. |
| `DELETE /v1/notes/{note_id}/refinement-proposal` | Reject and remove the displayed proposal. | When the user rejects it. | Note ID and optionally proposal ID/revision. | Updated note with the proposal removed. |

The proposal must use the same language as the original note. A result produced for an older note revision must not overwrite newer user edits. Whether accepting a proposal automatically runs AI processing again is open.

## Knowledge connections and graph

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/notes/{note_id}/connections` | Retrieve notes connected to the current note for a related-notes view. | When opening a note's connections panel. | Note ID and optional page size. | Connection IDs, labels/strength if exposed, and minimal connected-note summaries, limited to the same user and project. |
| `GET /v1/projects/{project_id}/knowledge-graph` | Retrieve graph nodes and edges for project visualization. | When opening or refreshing the project graph. | Project ID plus optional viewport/filter parameters (open). | Note nodes and knowledge-link edges for that project. |

The mobile app's ability to create, edit, or remove individual connections has not been specified; this proposal exposes AI-generated connections as read-only.

## Semantic search

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/projects/{project_id}/search` | Find relevant notes in the selected project by meaning and context instead of exact keywords. | When the user submits a search query while a project is selected. | Project ID in the path, query text, and pagination/filter options (open). | Matching note summaries, relevance scores if desired, and paging metadata. Results must be authorized against PostgreSQL so pending Qdrant deletion cannot expose deleted notes. |

## Chat with project knowledge

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/projects/{project_id}/conversations` | List a user's conversations in a project. | When opening the chat history for a project. | Project ID and pagination. | Conversation IDs, titles, and timestamps. |
| `POST /v1/projects/{project_id}/conversations` | Start a conversation scoped to the selected project. | When the user starts a new chat. | Optional conversation title (generation behavior open). | Created project-scoped conversation. |
| `GET /v1/conversations/{conversation_id}` | Load conversation history. | When opening a prior conversation. | Conversation ID and pagination/cursor. | Messages with roles, content, citations/source note IDs, and timestamps. |
| `POST /v1/conversations/{conversation_id}/messages` | Ask a question and receive an answer grounded in the conversation's project notes. | When the user sends a chat message. | User message text. | Complete assistant response in one response, source note references, and an explicit unsupported-answer outcome when project notes do not support an answer. |
| `DELETE /v1/conversations/{conversation_id}` | Delete a conversation and its chat history. | When the user deletes a conversation. | Conversation ID. | Deletion result. |

Conversation ownership, note-context scoping, and chat history must remain isolated per user. The assistant must clearly say when it cannot find a supported answer in the selected project's notes.

## Decisions needed before finalizing contracts

Note processing state values, polling behavior, queue recovery settings, and the remaining notes, refinement, search, knowledge graph, and chat API schemas remain open in their related feature documents. Do not implement those proposed routes until their corresponding contracts are approved.
