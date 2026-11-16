"""Adapters for providers exposing the OpenAI Chat Completions interface."""

from openai import OpenAI

from app.llm.ports import StructuredResult


class OpenAICompatibleStructuredTextGenerator:
    def __init__(
        self, api_key: str, base_url: str, model: str, provider_name: str
    ) -> None:
        self._model = model
        self._provider_name = provider_name
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[StructuredResult],
    ) -> StructuredResult:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": system_instruction,
                },
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        output = response.choices[0].message.content
        if not output or not output.strip():
            raise ValueError(f"{self._provider_name} returned an empty response")
        return response_model.model_validate_json(output)
