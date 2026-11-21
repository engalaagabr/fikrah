"""Worker and retrieval operations release provider clients before persistence."""

import asyncio
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.contracts.processing import NoteProcessingSnapshot
from app.llm.contracts import NoteAnalysis
from app.rag.errors import SearchUnavailableError
from app.rag.pipeline import NoteProcessingService
from app.rag.retriever import retrieve_current_notes


@pytest.mark.parametrize("fail_at", [None, "analysis", "embedding", "persistence"])
def test_worker_closes_each_provider_before_continuing(fail_at):
    events = []
    failure = ValueError("controlled provider workflow failure")
    snapshot = NoteProcessingSnapshot(
        job_id=uuid4(),
        note_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        revision=1,
        processing_generation=1,
        content="Thought",
        attempt_token="attempt",
    )

    def stage(name):
        events.append(name)
        if fail_at == name:
            raise failure

    class Generator:
        def generate_structured(self, **kwargs):
            stage("analysis")
            return NoteAnalysis(
                title="Title", refinement_proposal="Thought", concepts=[]
            )

        def close(self):
            events.append("close_text")

    class Embeddings:
        def embed_note(self, content):
            stage("embedding")
            return [0.1]

        def close(self):
            events.append("close_embedding")

    text_factory, embedding_factory = (
        Mock(side_effect=Generator),
        Mock(side_effect=Embeddings),
    )
    repository = Mock(claim=Mock(return_value=snapshot))

    def complete(snapshot, analysis, persist_vector):
        persist_vector()
        return True

    repository.complete_if_current.side_effect = complete
    vector_store = Mock(
        upsert_note=Mock(side_effect=lambda *_, **__: stage("persistence"))
    )
    service = NoteProcessingService(
        repository, vector_store, text_factory, embedding_factory, timedelta(minutes=5)
    )
    if fail_at is None:
        service.process(snapshot.job_id, "task")
        repository.fail_if_current.assert_not_called()
    else:
        with pytest.raises(ValueError) as caught:
            service.process(snapshot.job_id, "task")
        assert caught.value is failure
        repository.fail_if_current.assert_called_once_with(snapshot, terminal=False)
    expected = ["analysis", "close_text"]
    text_factory.assert_called_once()
    if fail_at == "analysis":
        embedding_factory.assert_not_called()
    else:
        embedding_factory.assert_called_once()
        expected.extend(["embedding", "close_embedding"])
        if fail_at != "embedding":
            expected.append("persistence")
    assert events == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", [None, "embedding", "vectors", "validation"])
async def test_retrieval_closes_embedding_before_vectors_and_validation(fail_at):
    events = []
    failure = ValueError("controlled retrieval failure")
    note_id = uuid4()

    def stage(name):
        events.append(name)
        if fail_at == name:
            raise failure

    class Embeddings:
        def embed_query(self, query):
            stage("embedding")
            return [0.1]

        def close(self):
            events.append("close_embedding")

    def vectors(*_):
        stage("vectors")
        return [(note_id, 1, 0.9)]

    async def validate(*_):
        stage("validation")
        return []

    repository = SimpleNamespace(find_completed_notes=AsyncMock(side_effect=validate))
    call = retrieve_current_notes(
        None,
        uuid4(),
        uuid4(),
        "Question",
        10,
        embedding_model_factory=Embeddings,
        vector_search=vectors,
        repository=repository,
    )
    if fail_at is None:
        assert await call == []
    elif fail_at == "validation":
        with pytest.raises(ValueError) as caught:
            await call
        assert caught.value is failure
    else:
        with pytest.raises(SearchUnavailableError) as caught:
            await call
        assert caught.value.__cause__ is failure
    expected = ["embedding", "close_embedding"]
    if fail_at != "embedding":
        expected.append("vectors")
        if fail_at != "vectors":
            expected.append("validation")
    assert events == expected


@pytest.mark.asyncio
async def test_cancelled_retrieval_does_not_close_a_running_embedding_request():
    started, release, closed = Event(), Event(), Event()

    class Embeddings:
        def embed_query(self, query):
            started.set()
            assert release.wait(5)
            return [0.1]

        def close(self):
            closed.set()

    vectors = Mock()
    repository = SimpleNamespace(find_completed_notes=AsyncMock())
    task = asyncio.create_task(
        retrieve_current_notes(
            None,
            uuid4(),
            uuid4(),
            "Question",
            10,
            embedding_model_factory=Embeddings,
            vector_search=vectors,
            repository=repository,
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not closed.is_set()
    finally:
        release.set()
        assert await asyncio.to_thread(closed.wait, 3)
    vectors.assert_not_called()
    repository.find_completed_notes.assert_not_called()
