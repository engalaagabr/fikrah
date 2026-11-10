# Project-Scoped Semantic Search

## Goal

Find relevant notes in the project currently selected by the user, including notes that do not share the query's exact words.

## API Contract

`POST /v1/projects/{project_id}/search` requires authentication and a project owned by the authenticated user.

Request:

```json
{
  "query": "ideas about building better habits",
  "limit": 10
}
```

`query` is trimmed, must contain non-whitespace text, and is limited to 4,000 characters. `limit` defaults to 10 and accepts 1–50.

The response is an ordered array of matching note summaries. Each result contains the note ID, title, content, relevance score, and last-updated timestamp. An empty array means no eligible indexed notes matched. Invalid or unowned project IDs return `404`; unavailable embedding or vector-search services return `503`.

## Retrieval and Isolation

1. Gemini converts the query to a vector using the `RETRIEVAL_QUERY` task type, paired with note vectors generated using `RETRIEVAL_DOCUMENT`.
2. Qdrant applies `user_id` and `project_id` payload filters before ranking and returns at most the requested number of note IDs, indexed revisions, and scores.
3. PostgreSQL hydrates note content and independently verifies user ownership, project membership, completed processing status, and that the indexed revision is still current. Deleted, moved, processing, or stale results are omitted.

Qdrant stores no raw note content. PostgreSQL is authoritative for access control and returned data. No database migration is required.

The search service returns framework-independent `SearchMatch` results from `app/search/contracts.py`. The HTTP route maps these results to the public `SearchResult` schema, and project chat consumes the same application contract without depending on SQLAlchemy note records.

## Scope

- Search is limited to the project identified in the route.
- Results are ranked by Qdrant similarity and returned in that order.
- Pagination, filters, score thresholds, and cross-project search are not included.
- The route does not wait for pending note processing; notes without a current completed vector do not appear.

## Verification

Tests cover Gemini retrieval task selection, project ownership, query normalization, and omission of stale, processing, and cross-user results.
