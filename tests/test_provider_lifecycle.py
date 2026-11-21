"""Provider resource ownership and cancellation safety without network requests."""

import asyncio
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.llm.lifecycle import run_with_provider
from app.llm.providers.deepseek import DeepSeekTextGenerator
from app.llm.providers.gemini import GeminiTextGenerator
from app.llm.providers.openrouter import OpenRouterTextGenerator
from app.rag.embeddings import GeminiEmbeddingModel


@pytest.mark.parametrize("fails", [False, True])
def test_owned_provider_closes_once_after_success_or_failure(fails):
    events = []

    class Provider:
        def __init__(self):
            events.append("create")

        def close(self):
            events.append("close")

    failure = ValueError("operation failed")

    def operation(provider):
        events.append("use")
        if fails:
            raise failure
        return 42

    if fails:
        with pytest.raises(ValueError) as caught:
            run_with_provider(Provider, operation)
        assert caught.value is failure
    else:
        assert run_with_provider(Provider, operation) == 42
    assert events == ["create", "use", "close"]


def test_factory_failure_does_not_attempt_to_close_an_uncreated_provider():
    operation = Mock()

    def factory():
        raise RuntimeError("could not create client")

    with pytest.raises(RuntimeError, match="could not create client"):
        run_with_provider(factory, operation)
    operation.assert_not_called()


@pytest.mark.parametrize(
    ("adapter_type", "args", "sdk"),
    [
        (DeepSeekTextGenerator, ("key", "model"), "openai"),
        (OpenRouterTextGenerator, ("key", "model"), "openai"),
        (GeminiTextGenerator, ("key", "model"), "gemini"),
        (GeminiEmbeddingModel, ("key", "model", 768), "gemini"),
    ],
)
def test_adapters_close_their_underlying_sdk_client(
    monkeypatch, adapter_type, args, sdk
):
    client = SimpleNamespace(close=Mock())
    sdk_constructor = Mock(return_value=client)
    if sdk == "openai":
        monkeypatch.setattr(
            "app.llm.providers.openai_compatible.OpenAI", sdk_constructor
        )
    else:
        monkeypatch.setattr("google.genai.Client", sdk_constructor)
    adapter = adapter_type(*args)
    adapter.close()
    sdk_constructor.assert_called_once()
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_cancellation_closes_client_only_after_background_operation_finishes():
    started, release, closed = Event(), Event(), Event()
    threads = []

    class Provider:
        def __init__(self):
            threads.append(get_ident())

        def close(self):
            threads.append(get_ident())
            closed.set()

    def operation(provider):
        threads.append(get_ident())
        started.set()
        assert release.wait(5)

    main_thread = get_ident()
    task = asyncio.create_task(
        asyncio.to_thread(run_with_provider, Provider, operation)
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
    assert len(threads) == 3
    assert len(set(threads)) == 1
    assert threads[0] != main_thread
