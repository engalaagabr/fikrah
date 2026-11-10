"""Validated input and output contracts shared across LLM use cases and adapters."""

from pydantic import BaseModel, Field


class NoteAnalysis(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    refinement_proposal: str = Field(min_length=1)
    concepts: list[str] = Field(max_length=8)


class ChatNoteContext(BaseModel):
    note_id: str
    title: str
    content: str


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class ChatAnswer(BaseModel):
    answer: str = Field(min_length=1)
    supported: bool
    source_note_ids: list[str] = Field(default_factory=list)
