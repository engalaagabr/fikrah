"""Application composition for configured LLM ports."""

import os

from app.infrastructure.llm.providers.deepseek import DeepSeekTextGenerator
from app.infrastructure.llm.providers.gemini import (
    GeminiEmbeddingModel,
    GeminiTextGenerator,
)
from app.infrastructure.llm.providers.openrouter import OpenRouterTextGenerator
from app.llm.ports import EmbeddingModel, StructuredTextGenerator


class LLMProviderFactory:
    """Build the configured text adapter and the fixed Gemini embedding adapter."""

    @staticmethod
    def create_text_generator(provider: str | None = None) -> StructuredTextGenerator:
        selected = (provider or os.getenv("LLM_TEXT_PROVIDER", "")).strip().lower()
        if selected == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY is required when LLM_TEXT_PROVIDER=deepseek"
                )
            return DeepSeekTextGenerator(
                api_key, os.getenv("DEEPSEEK_TEXT_MODEL", "deepseek-flash")
            )
        if selected == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is required when LLM_TEXT_PROVIDER=gemini"
                )
            return GeminiTextGenerator(
                api_key, os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
            )
        if selected == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is required when LLM_TEXT_PROVIDER=openrouter"
                )
            return OpenRouterTextGenerator(
                api_key,
                os.getenv("OPENROUTER_TEXT_MODEL", "deepseek/deepseek-v4.1-flash"),
            )
        raise RuntimeError(
            "LLM_TEXT_PROVIDER must be 'deepseek', 'gemini', or 'openrouter'"
        )

    @staticmethod
    def create_embedding_model() -> EmbeddingModel:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for note embeddings")
        dimensions = int(os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768"))
        if dimensions not in {768, 1536, 3072}:
            raise RuntimeError("GEMINI_EMBEDDING_DIMENSIONS must be 768, 1536, or 3072")
        return GeminiEmbeddingModel(
            api_key,
            os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            dimensions,
        )
