# Note Management API

## Status

The user approved the initial project-scoped note routes and processing states. The implementation adds text-note persistence, ownership checks, idempotent create requests, processing intents, deletion cleanup, Celery processing, and provider adapters.

## Confirmed Behavior

- Mobile sends text only. Audio transcription and PDF extraction remain local to the mobile app; the Backend stores only extracted text.
- Notes belong to one user and one project. A user cannot read, edit, move, or delete another user's note.
- Notes are created in the selected project; General remains the default project managed by the authentication flow.
- The Backend generates note IDs. A missing title remains `null` while processing is pending; mobile can display `Processing…` without storing it as a real title.
- Each create request includes an `Idempotency-Key`. Repeating the same key and body returns the created note; using that key with another body returns `409`. If the original note has since been deleted, replay returns `410` rather than recreating it.
- Every saved edit increments the note revision, sets state to `queued`, and stores a processing intent. Old revision results must not overwrite newer edits.
- Every processing request has a monotonically increasing generation so an older LLM attempt cannot replace a newer retry or refinement regeneration for the same note revision.
- Processing states are `queued`, `processing`, `completed`, and `failed`. Mobile polls `GET /v1/notes/{note_id}`. Polling interval/backoff remains mobile integration guidance.
- User-requested retry preserves the note and adds a processing intent for the current revision.
- Editing note content immediately clears a proposal made for the previous content. Editing only the title keeps the proposal while starting a new processing generation.
- Deleting a note or project deletes relational note connections and queued processing rows and writes a durable Qdrant cleanup request in the same database transaction. The actual vector deletion is asynchronous.
- HTTP request models stay in `app/notes/schemas.py`; routes map them to framework-independent commands in `app/notes/contracts.py` before calling `NoteService`. The service returns immutable results from `app/notes/results.py`, which routes map to public response schemas. The application service does not depend on Pydantic request or response schemas.

## API Contract

All routes require `Authorization: Bearer <access_token>`.

| Endpoint | Purpose and timing | Request | Response |
| --- | --- | --- | --- |
| `POST /v1/projects/{project_id}/notes` | Save captured text and begin processing. | `{ "content": "...", "title": "optional" }` plus `Idempotency-Key` header. | `201` with note ID, project, title, text, revision, processing state, and timestamps. |
| `GET /v1/projects/{project_id}/notes` | Load all notes when opening or refreshing a project. | Project ID in path. No pagination initially. | Notes ordered by most recently updated. |
| `GET /v1/notes/{note_id}` | Load a note and poll processing state. | Note ID in path. | Current note fields, concepts, optional refinement proposal, revision, processing generation, and state. |
| `PATCH /v1/notes/{note_id}` | Save content/title edits and reprocess. | At least one of `content` or `title`. Sending `title: null` clears it so LLM can generate a title. | Updated note at a new revision and `queued` state. |
| `DELETE /v1/notes/{note_id}` | Delete a note and its links. | Note ID in path. | `204`; vector cleanup proceeds asynchronously. |
| `POST /v1/notes/{note_id}/processing-retries` | Retry processing after failure or on request. | Note ID in path. | `202` with the current note and `queued` state. |
| `POST /v1/notes/{note_id}/refinement-regenerations` | Request another proposal for unchanged note content. | `{ "expected_processing_generation": 3 }` for the result currently displayed by the client. | `202` with the proposal cleared, incremented processing generation, and `queued` state. |
| `POST /v1/notes/{note_id}/refinement-acceptance` | Permanently replace the note's text with its displayed proposal and reprocess it. | `{ "expected_processing_generation": 3 }`. | `200` with the replaced content, cleared proposal, incremented note revision/generation, and `queued` state. |
| `POST /v1/notes/{note_id}/refinement-rejections` | Reject the displayed proposal while keeping note content unchanged. | `{ "expected_processing_generation": 3 }`. | `200` with the proposal cleared and unchanged content. |

The initial schema limits user-provided titles to 240 characters and requires nonblank note content. Project and note IDs that are unknown or owned by another user return `404`.

## Persistence

The migrations add `notes`, `note_processing_jobs`, `note_connections`, `note_idempotency_keys`, and `vector_cleanup_requests`. Note content and current state are stored in PostgreSQL. Processing intents are committed with note writes before queue publication; the API never puts note content into Redis. Idempotency keys are scoped to the user and currently retained persistently.

The Celery worker uses Redis as its broker, selects DeepSeek, Gemini, or OpenRouter for text analysis through `AIProviderFactory`, and uses Gemini embeddings for every note. Qdrant stores vectors under note IDs and metadata only; note text stays in PostgreSQL. The factory configuration and worker command are documented in `docs/features/note-processing/ai-provider-factory.md`.

## Verification

Tests cover note create/list/read/update/retry/delete, refinement accept/reject/regenerate actions, duplicate request replay and conflicts, user/project isolation, project deletion cleanup, provider selection, revision/generation-safe worker processing, durable queue dispatch, and Qdrant cleanup.
