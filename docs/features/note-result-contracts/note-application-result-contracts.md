# Note Application Result Contracts

## Goal

Keep note use cases independent from FastAPI response schemas and prevent SQLAlchemy note records from crossing into the HTTP layer.

## Design

- `app/notes/results.py` defines the immutable `NoteResult` returned by note application use cases.
- `NoteService` maps persisted note records to `NoteResult` for create, list, read, update, processing retry, and refinement actions.
- Idempotent create replay returns the same public result shape while preserving existing fingerprint and deleted-note behavior.
- `app/notes/routes.py` maps `NoteResult` values to the public `NoteView` schema.
- Concepts are tuples inside the application result and lists at the HTTP boundary.

## API Impact

There is no API contract or database schema change. Existing note fields, processing states, status codes, ownership checks, idempotency behavior, and deletion cleanup remain unchanged.
