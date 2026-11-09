from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import models

import app.search.service as search_service


def test_qdrant_search_filters_by_user_and_project_and_returns_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, project_id, note_id = uuid4(), uuid4(), uuid4()
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs

        def get_collections(self) -> SimpleNamespace:
            return SimpleNamespace(collections=[SimpleNamespace(name="fikrah-notes")])

        def query_points(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id=str(note_id), payload={"revision": 3}, score=0.91
                    ),
                    SimpleNamespace(id="not-a-uuid", payload={"revision": 1}, score=0.2),
                    SimpleNamespace(id=str(uuid4()), payload={}, score=0.1),
                ]
            )

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setenv("QDRANT_URL", "http://qdrant.test")
    monkeypatch.setattr(search_service, "QdrantClient", FakeClient)

    matches = search_service.search_note_vectors([0.1, 0.2], user_id, project_id, 7)

    assert matches == [(note_id, 3, pytest.approx(0.91))]
    search_filter = captured["query_filter"]
    assert isinstance(search_filter, models.Filter)
    assert [condition.key for condition in search_filter.must] == ["user_id", "project_id"]
    assert [condition.match.value for condition in search_filter.must] == [
        str(user_id),
        str(project_id),
    ]
    assert captured["limit"] == 7
    assert captured["with_payload"] == ["revision"]
    assert captured["closed"] is True


def test_qdrant_search_returns_empty_without_a_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def get_collections(self) -> SimpleNamespace:
            return SimpleNamespace(collections=[])

        def close(self) -> None:
            pass

    monkeypatch.setenv("QDRANT_URL", "http://qdrant.test")
    monkeypatch.setattr(search_service, "QdrantClient", FakeClient)

    assert search_service.search_note_vectors([0.1], uuid4(), uuid4(), 10) == []
