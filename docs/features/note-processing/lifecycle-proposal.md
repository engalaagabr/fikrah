# Note Processing Lifecycle Proposal

**Status: Proposal for review. The processing owner and API contract are not yet approved.**

## Confirmed Constraints

- Saving a note starts AI processing automatically.
- The user can request processing again.
- AI generates a title when the user did not supply one.
- Audio and PDF text extraction happens on mobile. The Backend receives text only.
- AI processing can produce concepts (up to eight), a project-scoped cluster, knowledge links, and a rewrite proposal.
- A rewrite proposal is surfaced only if the note has not changed while processing. Accepting it replaces the note text; rejecting it discards the proposal.
- A processing failure must not lose the note, and the user must be able to retry.

## Existing Mobile Integration Contract

`backend-integration.md` describes a mobile `NoteProcessor` that calls `AiService.analyze`, processes notes sequentially, allows up to 90 seconds, marks a note failed after an exception or timeout, and resumes unfinished work when the application opens again. The Backend API behavior behind that interface has not been defined. This client-side lifecycle should be reconciled with the Backend-owned persistence and AI responsibilities before integration.

## Options

| Approach | Lifecycle | Benefits | Costs and risks |
|---|---|---|---|
| Backend-owned asynchronous processing (recommended) | The API stores the note, starts a durable processing job, and returns its current state. The mobile app reads status and results from the Backend. | Processing can continue if the app closes; the Backend owns retries and durable state; the mobile app does not wait on a long AI request. | Requires durable job state and a worker. The API needs a status contract, and mobile needs to refresh or poll for completion. |
| Mobile-orchestrated processing | The mobile app calls an analysis endpoint and manages timeouts, retries, sequential execution, and resume behavior. | Matches the current `NoteProcessor` contract and needs less Backend job orchestration initially. | Work depends on app lifecycle and connectivity; mobile and Backend divide responsibility for failure and retry state. |

## Recommended Draft Flow

1. Mobile submits note text, its selected project, and an optional user-provided title.
2. The API verifies that the user owns the project, persists the note, and starts a durable processing job.
3. The API responds with the note and a processing state without waiting for AI completion.
4. A Backend worker processes the saved text. It generates a title only when the user did not provide one, then stores the supported insights and any rewrite proposal.
5. Mobile fetches the note and its processing state until the result is ready. Reopening the app does not restart completed work.
6. A failed job leaves the note intact. The user can ask the Backend to retry processing.

This proposal does not select job technology, endpoint paths, response schemas, or note identifiers. Those depend on approval of the lifecycle and the remaining mobile integration requirements.

## Questions Before API Design

- Should the Backend own durable asynchronous processing, or should the mobile app continue to orchestrate analysis requests?
- If Backend-owned, should the mobile app poll for state, or does the mobile application already provide a push/realtime mechanism?
- What identifier and idempotency contract should be used? The existing integration document says mobile-generated UUID v4 IDs, but that has not been confirmed for the Backend API.
- What should the mobile app display as the note title before AI finishes generating a missing title?
