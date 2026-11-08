# Note and Project Lifecycle Requirements

## Confirmed Behavior

- Every note has a title.
- A user-provided title is used when present.
- If a user does not provide a title, AI generates one as part of note processing after the note is saved.
- Deleting a project deletes every note associated with that project.
- Deleting a project or a note deletes all knowledge connections associated with the deleted notes.
- Deleting a project or a note also deletes all Qdrant embeddings associated with the deleted notes.
- The built-in `General` project is protected from deletion.

## Decisions Still Needed

- How cleanup and recovery are handled across PostgreSQL and Qdrant.

Do not create persistence models or deletion workflows that settle these open decisions implicitly.
