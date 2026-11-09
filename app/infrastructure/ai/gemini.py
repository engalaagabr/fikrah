"""Google Gemini text generation and embeddings adapters."""

from google import genai
from google.genai import types

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


class GeminiTextModel:
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=90_000)
        )

    def analyze_note(self, content: str) -> NoteAnalysis:
        response = self._client.models.generate_content(
            model=self._model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=NOTE_ANALYSIS_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=NoteAnalysis,
                max_output_tokens=3000,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty note analysis")
        return NoteAnalysis.model_validate_json(response.text)

    def answer_question(
        self,
        question: str,
        notes: list[ChatNoteContext],
        history: list[ChatHistoryMessage],
    ) -> ChatAnswer:
        response = self._client.models.generate_content(
            model=self._model,
            contents=build_chat_prompt(question, notes, history),
            config=types.GenerateContentConfig(
                system_instruction=CHAT_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ChatAnswer,
                max_output_tokens=3000,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty chat answer")
        return ChatAnswer.model_validate_json(response.text)


class GeminiEmbeddingModel:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=90_000)
        )

    def embed_note(self, content: str) -> list[float]:
        return self._embed(content, "RETRIEVAL_DOCUMENT")

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query, "RETRIEVAL_QUERY")

    def _embed(self, content: str, task_type: str) -> list[float]:
        response = self._client.models.embed_content(
            model=self._model,
            contents=content,
            config=types.EmbedContentConfig(
                task_type=task_type, output_dimensionality=self._dimensions
            ),
        )
        if not response.embeddings or not response.embeddings[0].values:
            raise ValueError("Gemini returned an empty embedding")
        return response.embeddings[0].values
