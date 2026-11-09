# Note Management API

## Status

The user approved the initial project-scoped note routes and processing states. The implementation adds text-note persistence, ownership checks, idempotent create requests, processing intents, and deletion cleanup. The AI worker still needs its provider integration before notes can reach a terminal processing state.

## Confirmed Behavior

- Mobile sends text only. Audio transcription and PDF extraction remain local to the mobile app; the Backend stores only extracted text.
- Notes belong to one user and one project. A user cannot read, edit, move, or delete another user's note.
- Notes are created in the selected project; General remains the default project managed by the authentication flow.
- The Backend generates note IDs. A missing title remains `null` while processing is pending; mobile can display `Processing…` without storing it as a real title.
- Each create request includes an `Idempotency-Key`. Repeating the same key and body returns the created note; using that key with another body returns `409`. If the original note has since been deleted, replay returns `410` rather than recreating it.
- Every saved edit increments the note revision, sets state to `queued`, and stores a processing intent. Old revision results must not overwrite newer edits.
- Processing states are `queued`, `processing`, `completed`, and `failed`. Mobile polls `GET /v1/notes/{note_id}`. Polling interval/backoff remains mobile integration guidance.
- User-requested retry preserves the note and adds a processing intent for the current revision.
- Deleting a note or project deletes relational note connections and queued processing rows and writes a durable Qdrant cleanup request in the same database transaction. The actual vector deletion is asynchronous.

## API Contract

All routes require `Authorization: Bearer <access_token>`.

| Endpoint | Purpose and timing | Request | Response |
| --- | --- | --- | --- |
| `POST /v1/projects/{project_id}/notes` | Save captured text and begin processing. | `{ "content": "...", "title": "optional" }` plus `Idempotency-Key` header. | `201` with note ID, project, title, text, revision, processing state, and timestamps. |
| `GET /v1/projects/{project_id}/notes` | Load all notes when opening or refreshing a project. | Project ID in path. No pagination initially. | Notes ordered by most recently updated. |
| `GET /v1/notes/{note_id}` | Load a note and poll processing state. | Note ID in path. | Current note fields and state. |
| `PATCH /v1/notes/{note_id}` | Save content/title edits and reprocess. | At least one of `content` or `title`. Sending `title: null` clears it so AI can generate a title. | Updated note at a new revision and `queued` state. |
| `DELETE /v1/notes/{note_id}` | Delete a note and its links. | Note ID in path. | `204`; vector cleanup proceeds asynchronously. |
| `POST /v1/notes/{note_id}/processing-retries` | Retry processing after failure or on request. | Note ID in path. | `202` with the current note and `queued` state. |

The initial schema limits user-provided titles to 240 characters and requires nonblank note content. Project and note IDs that are unknown or owned by another user return `404`.

## Persistence

The migration adds `notes`, `note_processing_jobs`, `note_connections`, `note_idempotency_keys`, and `vector_cleanup_requests`. Note content and current state are stored in PostgreSQL. Processing intents are committed with note writes before queue publication; the API never puts note content into Redis. Idempotency keys are scoped to the user and currently retained persistently.

The Celery worker uses Redis as its broker. The AI provider has not been selected yet, so the worker does not currently perform title generation, refinement, concept extraction, connection discovery, or embedding creation. Qdrant cleanup requests are stored durably for the future worker.

## Verification

Tests cover note create/list/read/update/retry/delete, duplicate request replay and conflicts, user/project isolation, and project deletion cleanup. The complete suite currently passes 14 tests.
