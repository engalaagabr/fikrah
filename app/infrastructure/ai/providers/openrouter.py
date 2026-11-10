"""OpenRouter text-generation adapter."""

from app.infrastructure.ai.providers.openai_compatible import (
    OpenAICompatibleTextModel,
)


class OpenRouterTextModel(OpenAICompatibleTextModel):
    """Route chat completions through OpenRouter's OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, "https://openrouter.ai/api/v1", model, "OpenRouter")
