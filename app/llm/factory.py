"""Application composition for configured LLM ports."""

from app.core.config import get_settings
from app.llm.ports import StructuredTextGenerator
from app.llm.providers.deepseek import DeepSeekTextGenerator
from app.llm.providers.gemini import GeminiTextGenerator
from app.llm.providers.openrouter import OpenRouterTextGenerator


class LLMProviderFactory:
    """Build the configured text-generation adapter."""

    @staticmethod
    def create_text_generator(provider: str | None = None) -> StructuredTextGenerator:
        """Return a fresh generator; the caller owns and must close its client."""
        settings = get_settings()
        selected = (provider or settings.llm_text_provider).strip().lower()
        if selected == "deepseek":
            api_key = settings.deepseek_api_key
            if not api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY is required when LLM_TEXT_PROVIDER=deepseek"
                )
            return DeepSeekTextGenerator(
                api_key, settings.deepseek_text_model
            )
        if selected == "gemini":
            api_key = settings.gemini_api_key
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is required when LLM_TEXT_PROVIDER=gemini"
                )
            return GeminiTextGenerator(
                api_key, settings.gemini_text_model
            )
        if selected == "openrouter":
            api_key = settings.openrouter_api_key
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is required when LLM_TEXT_PROVIDER=openrouter"
                )
            return OpenRouterTextGenerator(
                api_key,
                settings.openrouter_text_model,
            )
        raise RuntimeError(
            "LLM_TEXT_PROVIDER must be 'deepseek', 'gemini', or 'openrouter'"
        )
