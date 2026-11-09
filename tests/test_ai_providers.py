import pytest

import app.ai.providers as providers
from app.ai.providers import AIProviderFactory


def test_factory_selects_deepseek_or_gemini_text_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str, ...]] = []

    class FakeProvider:
        def __init__(self, *args: str) -> None:
            created.append(args)

    monkeypatch.setattr(providers, "DeepSeekTextModel", FakeProvider)
    monkeypatch.setattr(providers, "GeminiTextModel", FakeProvider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("DEEPSEEK_TEXT_MODEL", "deepseek-test-model")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-test-model")

    AIProviderFactory.create_text_model("deepseek")
    AIProviderFactory.create_text_model("gemini")

    assert created == [
        ("deepseek-test-key", "deepseek-test-model"),
        ("gemini-test-key", "gemini-test-model"),
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

    monkeypatch.setattr(providers, "GeminiEmbeddingModel", FakeEmbeddingProvider)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-test-embedding")
    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "1536")

    AIProviderFactory.create_embedding_model()
    assert created == [("gemini-test-key", "gemini-test-embedding", 1536)]

    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "512")
    with pytest.raises(RuntimeError, match="must be 768, 1536, or 3072"):
        AIProviderFactory.create_embedding_model()
