import pytest

import app.infrastructure.ai.factory as ai_factory
import app.infrastructure.ai.gemini as gemini_adapter
from app.infrastructure.ai.factory import AIProviderFactory


def test_factory_selects_deepseek_or_gemini_text_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str, ...]] = []

    class FakeProvider:
        def __init__(self, *args: str) -> None:
            created.append(args)

    monkeypatch.setattr(ai_factory, "DeepSeekTextModel", FakeProvider)
    monkeypatch.setattr(ai_factory, "GeminiTextModel", FakeProvider)
    monkeypatch.setattr(ai_factory, "OpenRouterTextModel", FakeProvider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("DEEPSEEK_TEXT_MODEL", "deepseek-test-model")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-test-model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")
    monkeypatch.setenv("OPENROUTER_TEXT_MODEL", "openrouter-test-model")

    AIProviderFactory.create_text_model("deepseek")
    AIProviderFactory.create_text_model("gemini")
    AIProviderFactory.create_text_model("openrouter")

    assert created == [
        ("deepseek-test-key", "deepseek-test-model"),
        ("gemini-test-key", "gemini-test-model"),
        ("openrouter-test-key", "openrouter-test-model"),
    ]


def test_factory_requires_selected_provider_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("AI_TEXT_PROVIDER", "deepseek")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        AIProviderFactory.create_text_model()

    monkeypatch.setenv("AI_TEXT_PROVIDER", "unsupported")
    with pytest.raises(RuntimeError, match="AI_TEXT_PROVIDER"):
        AIProviderFactory.create_text_model()


def test_embedding_factory_uses_gemini_and_validates_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str, ...]] = []

    class FakeEmbeddingProvider:
        def __init__(self, *args: str) -> None:
            created.append(args)

    monkeypatch.setattr(ai_factory, "GeminiEmbeddingModel", FakeEmbeddingProvider)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-test-embedding")
    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "1536")

    AIProviderFactory.create_embedding_model()
    assert created == [("gemini-test-key", "gemini-test-embedding", 1536)]

    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "512")
    with pytest.raises(RuntimeError, match="must be 768, 1536, or 3072"):
        AIProviderFactory.create_embedding_model()


def test_gemini_embedding_uses_document_and_query_retrieval_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_types: list[str] = []

    class Models:
        def embed_content(self, *, model: str, contents: str, config: object) -> object:
            task_types.append(config.task_type)
            return type("Response", (), {"embeddings": [type("Embedding", (), {"values": [0.1]})()]})()

    class Client:
        def __init__(self, **kwargs: object) -> None:
            self.models = Models()

    monkeypatch.setattr(gemini_adapter.genai, "Client", Client)
    embedding_model = gemini_adapter.GeminiEmbeddingModel("key", "model", 768)

    assert embedding_model.embed_note("a note") == [0.1]
    assert embedding_model.embed_query("a question") == [0.1]
    assert task_types == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
