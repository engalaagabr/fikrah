"""DeepSeek text-generation adapter."""

from app.infrastructure.ai.providers.openai_compatible import (
    OpenAICompatibleTextModel,
)


class DeepSeekTextModel(OpenAICompatibleTextModel):
    """Use DeepSeek's native OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, "https://api.deepseek.com", model, "DeepSeek")
