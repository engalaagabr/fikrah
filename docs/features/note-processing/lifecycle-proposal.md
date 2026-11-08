# Note Processing Lifecycle Proposal

**Status: Backend-owned asynchronous processing with Redis as the job broker is approved. Polling for status, Backend-generated note IDs, and reprocessing after every note save/edit are confirmed. The worker library, Redis durability configuration, and detailed API contracts remain open.**

## Confirmed Constraints

- Saving a note starts AI processing automatically.
- Saving an edit to an existing note also starts AI processing automatically.
- The Backend generates note IDs.
- Mobile polls the Backend to read note processing state.
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
| Backend-owned asynchronous processing with Redis — **approved** | The API stores the note and enqueues processing through Redis. A Backend worker processes jobs; PostgreSQL remains the source of truth for note and processing state. | Processing can continue if the app closes; the Backend owns durable state; the mobile app does not wait on a long AI request. | Requires a worker and deliberate Redis persistence/retry configuration. The API needs a status contract, and mobile needs a way to learn about completion. |
| Mobile-orchestrated processing — **not selected** | The mobile app calls an analysis endpoint and manages timeouts, retries, sequential execution, and resume behavior. | Matches the legacy `NoteProcessor` contract and needs less Backend job orchestration initially. | Work depends on app lifecycle and connectivity; mobile and Backend divide responsibility for failure and retry state. |

## Approved Lifecycle

1. Mobile submits note text, its selected project, and an optional user-provided title. The Backend generates the note ID.
2. The API verifies that the user owns the project, persists the note, and starts a durable processing job.
3. The API responds with the note and a processing state without waiting for AI completion.
4. A Backend worker processes the saved text. It generates a title only when the user did not provide one, then stores the supported insights and any rewrite proposal.
5. Mobile polls the note and its processing state until the result is ready. Reopening the app does not restart completed work.
6. A failed job leaves the note intact. The user can ask the Backend to retry processing.

Redis is selected as the job broker, not as a source of truth for notes or job results. This decision does not select a worker library, Redis persistence/retry configuration, endpoint paths, response schemas, polling interval, processing-state values, or request idempotency contract. Those depend on further architecture and mobile integration requirements.

## Questions Before API Design

- Which Redis-backed worker library should the Backend use?
- What Redis persistence and job retry settings are required to meet the durable-processing requirement?
- The idempotency retention period and response behavior if a key is reused with a different request body.
- The exact processing-state values and polling interval/backoff.

When a note is saved again while an earlier job is still running, the earlier result must not overwrite the newer note revision. The exact revision/idempotency mechanism remains an implementation detail for the API and persistence design.
