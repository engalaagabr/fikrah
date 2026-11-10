# Note and Project Lifecycle Requirements

## Confirmed Behavior

- Every note has a title.
- A user-provided title is used when present.
- If a user does not provide a title, LLM generates one as part of note processing after the note is saved.
- Deleting a project deletes every note associated with that project.
- Deleting a project or a note deletes all knowledge connections associated with the deleted notes.
- Deleting a project or a note also deletes all Qdrant embeddings associated with the deleted notes.
- The built-in `General` project is protected from deletion.
- PostgreSQL is authoritative for deletion. The same PostgreSQL transaction records a durable Qdrant cleanup request, and a worker retries cleanup until it succeeds.

## Decisions Still Needed

- How synchronization and recovery for non-deletion writes are handled across PostgreSQL and Qdrant.

## Deletion Consistency

Deletion is eventually consistent across PostgreSQL and Qdrant: the PostgreSQL deletion and cleanup request commit together, while Qdrant cleanup may complete afterward. Until cleanup completes, reads must validate returned note identifiers against PostgreSQL so deleted notes are not surfaced.

Do not create persistence models or deletion workflows that settle these open decisions implicitly.
