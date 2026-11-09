# Note Refinement Proposal Actions

## Status

Implemented. This feature lets a user accept, reject, or regenerate the AI rewrite proposal produced during note processing.

## Confirmed behavior

- AI proposes a rewrite in the original note's language while preserving its meaning.
- The proposal does not replace note content until the user accepts it.
- Accepting permanently replaces the current content with the proposal; no previous-content version is retained. The accepted text is processed like any saved edit.
- Rejecting removes the proposal and leaves note content unchanged. The user can later request another wording.
- Regenerating removes the current proposal and queues analysis of the unchanged content.
- Editing note content clears a proposal made for older content.
- The mobile client sends the `processing_generation` it received with the note. A stale proposal action returns `409` so an action cannot apply to a newer proposal that the user has not seen.

## API contract

All routes require authentication and verify ownership through the note's user ID.

| Endpoint | Purpose and timing | Request | Response |
| --- | --- | --- | --- |
| `POST /v1/notes/{note_id}/refinement-regenerations` | Request a new proposal after rejecting or when the user wants another wording. | `{ "expected_processing_generation": 3 }` | `202` with the current note, cleared proposal, incremented processing generation, and `queued` state. |
| `POST /v1/notes/{note_id}/refinement-acceptance` | Apply the displayed proposal and begin processing the accepted content. | `{ "expected_processing_generation": 3 }` | `200` with replaced content, cleared proposal, incremented note revision and processing generation, and `queued` state. |
| `POST /v1/notes/{note_id}/refinement-rejections` | Reject the displayed proposal. | `{ "expected_processing_generation": 3 }` | `200` with the proposal removed and note content unchanged. |

`GET /v1/notes/{note_id}` includes `processing_generation`. A generation changes whenever a processing attempt is requested, a note is saved, or a proposal is accepted/regenerated. Workers discard results whose revision or generation is no longer current.

## Persistence and processing

PostgreSQL stores the proposal and processing generation. The generation is copied to durable processing-job rows. Celery workers verify both the note revision and generation before beginning and before committing AI results. Regeneration reuses the note-processing worker and provider factory. The stored note content remains unchanged while the worker refreshes analysis and writes an embedding for the same content.

## Verification

Tests cover accepting and permanently replacing note content, rejecting without changing content, regenerating while retaining the original text, stale-generation conflicts, and workers ignoring a superseded generation.
