"""Application composition for configured LLM ports."""

import os

from app.ai.ports import EmbeddingModel, TextModel
from app.infrastructure.ai.providers.deepseek import DeepSeekTextModel
from app.infrastructure.ai.providers.gemini import (
    GeminiEmbeddingModel,
    GeminiTextModel,
)
from app.infrastructure.ai.providers.openrouter import OpenRouterTextModel


class AIProviderFactory:
    """Build the configured text adapter and the fixed Gemini embedding adapter."""

    @staticmethod
    def create_text_model(provider: str | None = None) -> TextModel:
        selected = (provider or os.getenv("AI_TEXT_PROVIDER", "")).strip().lower()
        if selected == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY is required when AI_TEXT_PROVIDER=deepseek"
                )
            return DeepSeekTextModel(
                api_key, os.getenv("DEEPSEEK_TEXT_MODEL", "deepseek-flash")
            )
        if selected == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is required when AI_TEXT_PROVIDER=gemini"
                )
            return GeminiTextModel(
                api_key, os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
            )
        if selected == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is required when AI_TEXT_PROVIDER=openrouter"
                )
            return OpenRouterTextModel(
                api_key,
                os.getenv("OPENROUTER_TEXT_MODEL", "deepseek/deepseek-v4.1-flash"),
            )
        raise RuntimeError(
            "AI_TEXT_PROVIDER must be 'deepseek', 'gemini', or 'openrouter'"
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
