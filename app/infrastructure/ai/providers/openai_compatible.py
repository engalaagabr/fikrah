"""Adapters for providers exposing the OpenAI Chat Completions interface."""

from __future__ import annotations

from openai import OpenAI

from app.ai.contracts import (
    ChatAnswer,
    ChatHistoryMessage,
    ChatNoteContext,
    NoteAnalysis,
)
from app.ai.prompts import (
    CHAT_SYSTEM_PROMPT,
    NOTE_ANALYSIS_SYSTEM_PROMPT,
    build_chat_prompt,
)


class OpenAICompatibleTextModel:
    def __init__(
        self, api_key: str, base_url: str, model: str, provider_name: str
    ) -> None:
        self._model = model
        self._provider_name = provider_name
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)

    def analyze_note(self, content: str) -> NoteAnalysis:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": NOTE_ANALYSIS_SYSTEM_PROMPT + " Output valid JSON.",
                },
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        output = response.choices[0].message.content
        if not output or not output.strip():
            raise ValueError(f"{self._provider_name} returned an empty note analysis")
        return NoteAnalysis.model_validate_json(output)

    def answer_question(
        self,
        question: str,
        notes: list[ChatNoteContext],
        history: list[ChatHistoryMessage],
    ) -> ChatAnswer:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": CHAT_SYSTEM_PROMPT + " Output valid JSON.",
                },
                {
                    "role": "user",
                    "content": build_chat_prompt(question, notes, history),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        output = response.choices[0].message.content
        if not output or not output.strip():
            raise ValueError(f"{self._provider_name} returned an empty chat answer")
        return ChatAnswer.model_validate_json(output)
