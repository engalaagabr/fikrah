"""Application-facing interfaces implemented by AI infrastructure adapters."""

from typing import Protocol

from app.ai.contracts import ChatAnswer, ChatHistoryMessage, ChatNoteContext, NoteAnalysis


class TextModel(Protocol):
    def analyze_note(self, content: str) -> NoteAnalysis: ...

    def answer_question(
        self,
        question: str,
        notes: list[ChatNoteContext],
        history: list[ChatHistoryMessage],
    ) -> ChatAnswer: ...


class EmbeddingModel(Protocol):
    def embed_note(self, content: str) -> list[float]: ...

    def embed_query(self, query: str) -> list[float]: ...
