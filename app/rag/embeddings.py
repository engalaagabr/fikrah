"""Gemini embedding adapter and configuration factory."""

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.llm.ports import EmbeddingModel


class GeminiEmbeddingModel:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=90_000)
        )

    def close(self) -> None:
        self._client.close()

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


def create_embedding_model() -> EmbeddingModel:
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for note embeddings")
    dimensions = int(settings.gemini_embedding_dimensions)
    if dimensions not in {768, 1536, 3072}:
        raise RuntimeError("GEMINI_EMBEDDING_DIMENSIONS must be 768, 1536, or 3072")
    return GeminiEmbeddingModel(
        api_key,
        settings.gemini_embedding_model,
        dimensions,
    )
