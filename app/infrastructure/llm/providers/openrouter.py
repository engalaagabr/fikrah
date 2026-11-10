"""OpenRouter text-generation adapter."""

from app.infrastructure.llm.providers.openai_compatible import (
    OpenAICompatibleStructuredTextGenerator,
)


class OpenRouterTextGenerator(OpenAICompatibleStructuredTextGenerator):
    """Route chat completions through OpenRouter's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, "https://openrouter.ai/api/v1", model, "OpenRouter")
