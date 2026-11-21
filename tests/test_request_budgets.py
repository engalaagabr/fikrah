"""Atomic budget, input-limit and hashing-capacity regressions."""

import asyncio
import os
from threading import Event
from uuid import uuid4

import pytest

from app.api.body_limits import RequestBodyLimitMiddleware
from app.core.security import PasswordWorkBusy, run_password_work
from app.infrastructure.rate_limits import RedisBudgetStore
from app.schemas.notes import NoteCreate, NoteUpdate, ProposalUpdate
from app.services.request_budgets import RequestBudgetExceeded, RequestBudgetUnavailable


@pytest.mark.asyncio
async def test_redis_budget_is_atomic_under_concurrency():
    url = os.getenv("FIKRAH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set FIKRAH_TEST_REDIS_URL to an isolated Redis test instance")
    store = RedisBudgetStore(lambda: url)
    key = f"atomic-test:{uuid4()}"
    results = await asyncio.gather(
        *(store.consume(key, 5, 60) for _ in range(20)), return_exceptions=True
    )
    assert sum(result is None for result in results) == 5
    blocked = [
        result for result in results if isinstance(result, RequestBudgetExceeded)
    ]
    assert len(blocked) == 15
    assert all(1 <= error.retry_after <= 60 for error in blocked)
    # A different identity has a separate budget.
    await store.consume(f"other:{key}", 5, 60)


@pytest.mark.asyncio
async def test_redis_budget_does_not_fail_open_on_outage():
    store = RedisBudgetStore(lambda: "redis://127.0.0.1:1/0")
    with pytest.raises(RequestBudgetUnavailable):
        await store.consume("unavailable-test", 5, 60)


@pytest.mark.parametrize("model", [NoteCreate, NoteUpdate, ProposalUpdate])
def test_note_inputs_enforce_configured_character_limit(monkeypatch, model):
    monkeypatch.setenv("FIKRAH_NOTE_MAX_CHARACTERS", "10")
    kwargs = {"content": "x" * 11}
    if model is ProposalUpdate:
        kwargs = {"refinement_proposal": "x" * 11, "expected_processing_generation": 1}
    with pytest.raises(ValueError, match="10 characters"):
        model(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("declared_length", [False, True])
async def test_body_limit_rejects_declared_and_chunked_oversize(
    monkeypatch, declared_length
):
    monkeypatch.setenv("FIKRAH_REQUEST_MAX_BYTES", "10")
    called = []
    sent = []

    async def downstream(*_):
        called.append(True)

    chunks = iter([b"123456", b"789012"])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-length", b"12")] if declared_length else [],
    }
    await RequestBodyLimitMiddleware(downstream)(scope, receive, send)
    assert called == []
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_password_work_has_bounded_concurrency():
    release = Event()
    started = [Event() for _ in range(4)]

    def work(index):
        started[index].set()
        assert release.wait(5)
        return index

    tasks = [asyncio.create_task(run_password_work(work, index)) for index in range(4)]
    try:
        await asyncio.wait_for(
            asyncio.to_thread(lambda: all(event.wait(3) for event in started)),
            timeout=4,
        )
        with pytest.raises(PasswordWorkBusy):
            await run_password_work(lambda: None)
    finally:
        release.set()
        assert await asyncio.gather(*tasks) == [0, 1, 2, 3]
