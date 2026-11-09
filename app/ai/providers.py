"""AI text and embedding provider adapters."""

from __future__ import annotations

import json
import os
from typing import Protocol

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field


class NoteAnalysis(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    refinement_proposal: str = Field(min_length=1)
    concepts: list[str] = Field(max_length=8)


class TextModel(Protocol):
    def analyze_note(self, content: str) -> NoteAnalysis: ...


class EmbeddingModel(Protocol):
    def embed_note(self, content: str) -> list[float]: ...

    def embed_query(self, query: str) -> list[float]: ...


_SYSTEM_INSTRUCTION = """You analyze personal knowledge notes. Return only a JSON object with exactly these fields:
title, refinement_proposal, concepts.
Write title and refinement_proposal in the same language as the original note.
Preserve the author's meaning. The refinement is a clearer rewrite suggestion, not a replacement.
Extract at most eight concise concepts. Do not invent facts or add advice.
"""


class DeepSeekTextModel:
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=90)

    def analyze_note(self, content: str) -> NoteAnalysis:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_INSTRUCTION + " Output valid JSON."},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        output = response.choices[0].message.content
        if not output or not output.strip():
            raise ValueError("DeepSeek returned an empty note analysis")
        return NoteAnalysis.model_validate(json.loads(output))


class GeminiTextModel:
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90_000))

    def analyze_note(self, content: str) -> NoteAnalysis:
        response = self._client.models.generate_content(
            model=self._model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=NoteAnalysis,
                max_output_tokens=3000,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty note analysis")
        return NoteAnalysis.model_validate_json(response.text)


class GeminiEmbeddingModel:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90_000))

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


class AIProviderFactory:
    """Build the configured text provider and the fixed Gemini embedding provider."""

    @staticmethod
    def create_text_model(provider: str | None = None) -> TextModel:
        selected = (provider or os.getenv("AI_TEXT_PROVIDER", "")).strip().lower()
        if selected == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is required when AI_TEXT_PROVIDER=deepseek")
            return DeepSeekTextModel(api_key, os.getenv("DEEPSEEK_TEXT_MODEL", "deepseek-flash"))
        if selected == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is required when AI_TEXT_PROVIDER=gemini")
            return GeminiTextModel(api_key, os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash"))
        raise RuntimeError("AI_TEXT_PROVIDER must be either 'deepseek' or 'gemini'")

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
