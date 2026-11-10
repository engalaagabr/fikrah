"""Qdrant vector-store adapter used by search and chat use cases."""

from __future__ import annotations

import os
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.search.errors import SearchUnavailableError


class QdrantNoteVectorStore:
    """Qdrant adapter for note indexing, removal, and semantic retrieval."""

    def __init__(self) -> None:
        self._url = os.getenv("QDRANT_URL")
        self._api_key = os.getenv("QDRANT_API_KEY")
        self._collection = os.getenv("QDRANT_NOTES_COLLECTION", "fikrah-notes")
        self._dimensions = int(os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768"))

    def _client(self) -> QdrantClient:
        if not self._url:
            raise SearchUnavailableError("QDRANT_URL is required for vector storage")
        return QdrantClient(url=self._url, api_key=self._api_key, timeout=30)

    def _ensure_collection(self, client: QdrantClient) -> None:
        collections = {item.name for item in client.get_collections().collections}
        if self._collection in collections:
            return
        try:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(
                    size=self._dimensions, distance=models.Distance.COSINE
                ),
            )
        except Exception:
            # Concurrent workers may create the collection at the same time.
            collections = {item.name for item in client.get_collections().collections}
            if self._collection not in collections:
                raise

    def upsert_note(
        self,
        note_id: UUID,
        vector: list[float],
        *,
        user_id: UUID,
        project_id: UUID,
        revision: int,
        processing_generation: int,
    ) -> None:
        if len(vector) != self._dimensions:
            raise ValueError(
                f"Expected {self._dimensions}-dimensional embedding, received {len(vector)}"
            )
        client = self._client()
        try:
            self._ensure_collection(client)
            client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=str(note_id),
                        vector=vector,
                        payload={
                            "user_id": str(user_id),
                            "project_id": str(project_id),
                            "revision": revision,
                            "processing_generation": processing_generation,
                        },
                    )
                ],
                wait=True,
            )
        finally:
            client.close()

    def delete_note(self, note_id: UUID) -> None:
        client = self._client()
        try:
            collections = {item.name for item in client.get_collections().collections}
            if self._collection in collections:
                client.delete(
                    collection_name=self._collection,
                    points_selector=models.PointIdsList(points=[str(note_id)]),
                    wait=True,
                )
        finally:
            client.close()

    def search_notes(
        self, query_vector: list[float], user_id: UUID, project_id: UUID, limit: int
    ) -> list[tuple[UUID, int, float]]:
        """Return indexed revisions and scores for one user's project."""
        client = self._client()
        try:
            collections = {item.name for item in client.get_collections().collections}
            if self._collection not in collections:
                return []
            response = client.query_points(
                collection_name=self._collection,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id", match=models.MatchValue(value=str(user_id))
                        ),
                        models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=str(project_id)),
                        ),
                    ]
                ),
                limit=limit,
                with_payload=["revision"],
                with_vectors=False,
            )
            matches: list[tuple[UUID, int, float]] = []
            for point in response.points:
                revision = (point.payload or {}).get("revision")
                if revision is None:
                    continue
                try:
                    matches.append(
                        (UUID(str(point.id)), int(revision), float(point.score))
                    )
                except (TypeError, ValueError):
                    continue
            return matches
        except SearchUnavailableError:
            raise
        except Exception as exc:
            raise SearchUnavailableError("Qdrant search failed") from exc
        finally:
            client.close()


def search_note_vectors(
    query_vector: list[float], user_id: UUID, project_id: UUID, limit: int
) -> list[tuple[UUID, int, float]]:
    """Return note IDs, indexed revisions, and scores for one user's project."""
    return QdrantNoteVectorStore().search_notes(
        query_vector, user_id, project_id, limit
    )
