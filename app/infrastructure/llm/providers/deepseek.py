"""DeepSeek text-generation adapter."""

from app.infrastructure.llm.providers.openai_compatible import (
    OpenAICompatibleStructuredTextGenerator,
)


class DeepSeekTextGenerator(OpenAICompatibleStructuredTextGenerator):
    """Use DeepSeek's native OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, "https://api.deepseek.com", model, "DeepSeek")
