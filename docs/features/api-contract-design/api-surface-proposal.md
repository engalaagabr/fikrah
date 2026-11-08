# Proposed Mobile API Surface

**Status: Proposal for review.** Product behaviors listed as confirmed come from `docs/product/ai-backend-scope.md`. Paths, HTTP methods, and payloads below are candidate contracts, not approved implementation requirements.

## Contract-wide rules

- All endpoints except account registration, login, Google sign-in, and token refresh require an authenticated user.
- Every database and vector lookup is scoped to the authenticated user's data. The client does not choose or submit an owner ID.
- Note content sent to the Backend is plain text. The mobile app extracts voice and PDF text locally, and original PDFs remain on-device. There is no file upload or server-side extraction endpoint in this proposal.
- Project-scoped operations verify that the selected project belongs to the authenticated user. `General` is the default project and cannot be deleted.
- Deleting a project removes its notes; deleting a note or project also removes associated knowledge links and schedules durable Qdrant cleanup.
- Suggested refinement text is a proposal. Accepting replaces the current note text permanently; rejecting removes the proposal. A user can request another proposal.
- Responses should use stable resource IDs and explicit processing state. Exact ID generation, error format, pagination, and timestamp conventions remain open.

## Authentication and account

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/auth/register` | Create an email/password account and its protected `General` project. | When a user signs up with email. | Email and password; any required verification data is undecided. | Account identity, authentication credentials/tokens if registration signs the user in, and the default project identity. |
| `POST /v1/auth/login` | Authenticate an existing email/password account. | At email/password sign-in. | Email and password. | Account identity and authentication credentials/tokens. |
| `POST /v1/auth/google` | Authenticate or create an account using Google. | After the mobile Google sign-in flow obtains a provider credential. | Google credential from the mobile client; exact credential type and verification flow are undecided. | Account identity and authentication credentials/tokens. |
| `POST /v1/auth/refresh` | Renew an expired short-lived access credential without asking the user to sign in again. | When the mobile client receives an expired/near-expiry access credential. | Refresh credential, if the selected token model uses one. | New access credential and optionally a rotated refresh credential. |
| `POST /v1/auth/logout` | End the current authenticated session if credentials are revocable. | When the user signs out. | Current session or refresh credential, depending on the token model. | Confirmation that the session was ended. |
| `GET /v1/users/me` | Return the current account identity needed for account state and profile display. | On app startup or when account state must be refreshed. | No body; authenticated context identifies the account. | Account ID, email, and supported profile fields. |

Email verification, password recovery, account deletion, concurrent sessions, and profile editing need product decisions before they are added to the contract.

## Projects

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
| `POST /v1/projects/{project_id}/notes` | Save a note and start Backend-owned AI processing. | After the user saves text or locally extracted audio/PDF text. | Plain text, optional user title, and possibly a client-generated idempotency key (open). No file. | Saved note ID, selected project ID, current title if supplied, processing state, and creation/update times. |
| `GET /v1/projects/{project_id}/notes` | List notes for a project. | When opening or refreshing a project. | Pagination and filters (open). | Notes with IDs, titles, processing states, and list-preview fields to be agreed. |
| `GET /v1/notes/{note_id}` | Fetch the latest note and AI processing result. | When opening a note, after processing completes, or after a retry. | Note ID in the path. | Current text/title, processing state, concepts, cluster, refinement proposal if any, connections or their IDs, and timestamps. Exact shape is open. |
| `PATCH /v1/notes/{note_id}` | Save user edits to note text or title. | When the user saves a note edit. | Changed text and/or title. | Updated note and processing state. Whether editing automatically starts another processing job is unresolved. |
| `DELETE /v1/notes/{note_id}` | Delete a note and its connections and associated vector. | When the user confirms note deletion. | Note ID in the path. | Deletion result; vector cleanup may finish asynchronously. |
| `POST /v1/notes/{note_id}/processing-retries` | Retry AI processing while preserving the note. | When the user requests reprocessing or a previous attempt failed. | Note ID in the path; optional retry reason is not required by current product behavior. | Accepted retry state/job reference and current note processing state. |

AI generates a title during processing only when the user did not supply one. The temporary title behavior while a note is pending is not settled. Processing status delivery (polling, server-sent events, push, or another app-supported mechanism) and the exact state values need a decision.

## Refinement proposals

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `POST /v1/notes/{note_id}/refinement-regenerations` | Generate a new wording proposal after the user rejected the previous one or requests another version. | When the user asks for another rewrite. | Note ID; optionally the unchanged source-text version to prevent applying a stale result. | Accepted processing state and later a proposal in the note response. |
| `POST /v1/notes/{note_id}/refinement-acceptance` | Apply the currently displayed proposal by replacing the note text permanently. | When the user accepts the proposal. | Proposal ID or note revision to prevent accepting a stale proposal (exact concurrency contract open). | Updated note text, cleared proposal, and processing state if acceptance triggers reprocessing (open). |
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
| `POST /v1/search` | Find relevant notes by meaning and context instead of exact keywords. | When the user submits a search query. | Query text, optional project ID (all user projects vs selected project is open), and pagination/filter options (open). | Matching note summaries, relevance scores if desired, and paging metadata. Results must be authorized against PostgreSQL so pending Qdrant deletion cannot expose deleted notes. |

## Chat with project knowledge

| Proposed endpoint | Purpose and why mobile needs it | When mobile calls it | Request information | Response information |
|---|---|---|---|---|
| `GET /v1/projects/{project_id}/conversations` | List a user's conversations in a project. | When opening the chat history for a project. | Project ID and pagination. | Conversation IDs, titles, and timestamps. |
| `POST /v1/projects/{project_id}/conversations` | Start a conversation scoped to a project. | When the user starts a new chat. | Optional conversation title (generation behavior open). | Created conversation. |
| `GET /v1/conversations/{conversation_id}` | Load conversation history. | When opening a prior conversation. | Conversation ID and pagination/cursor. | Messages with roles, content, citations/source note IDs, and timestamps. |
| `POST /v1/conversations/{conversation_id}/messages` | Ask a question and receive an answer grounded in the conversation's project notes. | When the user sends a chat message. | User message text. | Assistant response, source note references, and an explicit unsupported-answer outcome when project notes do not support an answer. Streaming vs one response is open. |
| `DELETE /v1/conversations/{conversation_id}` | Delete a conversation and its chat history. | When the user deletes a conversation. | Conversation ID. | Deletion result. |

Conversation ownership, note-context scoping, and chat history must remain isolated per user. The assistant must clearly say when it cannot find a supported answer in the selected project's notes.

## Decisions needed before finalizing contracts

1. **Authentication session:** Should mobile use short-lived access tokens plus rotating refresh tokens, and should the API accept a Google ID token from mobile or use a Backend OAuth redirect flow?
2. **Account recovery:** Are email verification and password reset required in the first release?
3. **Processing updates:** Should mobile poll note state, or does the mobile app already have push/realtime infrastructure we should integrate with?
4. **Note identity:** Should note IDs be generated by the Backend, or does mobile need to submit its existing client-generated UUID for offline/idempotent saves?
5. **Editing behavior:** Does saving a manual note edit automatically re-run AI processing, or only when the user explicitly asks?
6. **Temporary title:** What should mobile display for a note with no user title until AI generates one?
7. **Search scope and chat:** Is search limited to the selected project by default? Should chat conversations always belong to exactly one project?
8. **Refinement acceptance:** After acceptance replaces note text, should the Backend automatically reprocess the accepted text to refresh concepts, links, and embeddings?
9. **Streaming:** Should chat return a complete response or stream tokens to mobile?

Do not implement these proposed routes or infer answers to these questions until the corresponding contracts are approved.
