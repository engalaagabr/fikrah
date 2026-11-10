"""Application-facing interfaces implemented by LLM infrastructure adapters."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

StructuredResult = TypeVar("StructuredResult", bound=BaseModel)


class StructuredTextGenerator(Protocol):
    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[StructuredResult],
    ) -> StructuredResult: ...


class EmbeddingModel(Protocol):
    def embed_note(self, content: str) -> list[float]: ...

    def embed_query(self, query: str) -> list[float]: ...
