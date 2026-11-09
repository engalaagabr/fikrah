"""Qdrant vector-store adapter used by search and chat use cases."""

from __future__ import annotations

import os
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.search.errors import SearchUnavailableError


def search_note_vectors(
    query_vector: list[float], user_id: UUID, project_id: UUID, limit: int
) -> list[tuple[UUID, int, float]]:
    """Return note IDs, indexed revisions, and scores for one user's project."""
    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        raise SearchUnavailableError("QDRANT_URL is required for semantic search")

    collection_name = os.getenv("QDRANT_NOTES_COLLECTION", "fikrah-notes")
    client = QdrantClient(
        url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY"), timeout=30
    )
    try:
        collections = {item.name for item in client.get_collections().collections}
        if collection_name not in collections:
            return []

        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=str(user_id))
                    ),
                    models.FieldCondition(
                        key="project_id", match=models.MatchValue(value=str(project_id))
                    ),
                ]
            ),
            limit=limit,
            with_payload=["revision"],
            with_vectors=False,
        )
        matches: list[tuple[UUID, int, float]] = []
        for point in response.points:
            payload = point.payload or {}
            revision = payload.get("revision")
            if revision is None:
                continue
            try:
                matches.append((UUID(str(point.id)), int(revision), float(point.score)))
            except (TypeError, ValueError):
                continue
        return matches
    except SearchUnavailableError:
        raise
    except Exception as exc:
        raise SearchUnavailableError("Qdrant search failed") from exc
    finally:
        client.close()
