# Note and Project Lifecycle Requirements

## Confirmed Behavior

- Every note has a title.
- A user-provided title is used when present.
- If a user does not provide a title, the system supplies one.
- Deleting a project deletes every note associated with that project.

## Decisions Still Needed

- Whether the system-generated title comes from AI or a deterministic text rule, and when it becomes available.
- Whether deleting a project also removes its notes' knowledge connections and Qdrant vectors.
- Whether the built-in `General` project can be deleted.

Do not create persistence models or deletion workflows that settle these open decisions implicitly.
