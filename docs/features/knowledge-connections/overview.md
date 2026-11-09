# Knowledge Connections and Project Graph

## Goal

Connect related notes in a project and give mobile clients read-only APIs for related notes and graph visualization.

## Connection Rule

When note processing completes, the worker compares its extracted concepts with completed notes belonging to the same user and project. A relationship is created when at least one concept matches after trimming whitespace and comparing case-insensitively. Candidates are ranked by number of shared concepts, then by most recent update; at most ten candidates are linked per processing run.

The worker stores a directed link from the note it just processed to each matched note. Reprocessing refreshes that note's outgoing links, removing links that no longer share a concept. PostgreSQL serializes relationship refreshes within each project so concurrently completed notes can observe one another. Retrieval treats links as undirected and deduplicates pairs if both notes independently selected one another.

## API

All routes require authentication and return only the authenticated user's notes.

### `GET /v1/notes/{note_id}/connections`

Returns related completed notes for the requested note, including inbound or outbound generated links:

```json
[
  {
    "note_id": "uuid",
    "title": "A note title",
    "shared_concepts": ["Planning"],
    "updated_at": "2026-11-09T18:30:00Z"
  }
]
```

An unknown or unowned note returns `404`. A note that is not currently completed returns an empty list.

### `GET /v1/projects/{project_id}/knowledge-graph`

Returns all completed notes in the owned project as `nodes` and their current shared-concept links as `edges`. Nodes contain ID, title, concepts, and update timestamp. Edges contain source and target note IDs plus the concepts shared by both notes. Repeated links in both directions are returned as one undirected edge; source/target ordering is stable but has no semantic meaning. Unknown or unowned projects return `404`.

The initial graph response has no pagination or viewport filtering. Pending and failed notes are omitted.

## Persistence and Lifecycle

Connections use the existing `note_connections` PostgreSQL table. No migration is needed. Existing note and project deletion flows already remove every connection involving deleted notes. Qdrant vectors and note text are not changed by relation generation.

## Verification

Tests cover normalized concept matching, same-user and same-project isolation, stale-link removal, retrieval response shape, and graph ownership boundaries.
