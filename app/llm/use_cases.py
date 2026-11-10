"""Application-level LLM workflows and prompt composition."""

from app.llm.contracts import (
    ChatAnswer,
    ChatHistoryMessage,
    ChatNoteContext,
    NoteAnalysis,
)
from app.llm.ports import StructuredTextGenerator
from app.llm.prompts import (
    CHAT_SYSTEM_PROMPT,
    NOTE_ANALYSIS_SYSTEM_PROMPT,
    build_chat_prompt,
)


def analyze_note(text_generator: StructuredTextGenerator, content: str) -> NoteAnalysis:
    return text_generator.generate_structured(
        system_instruction=NOTE_ANALYSIS_SYSTEM_PROMPT,
        user_content=content,
        response_model=NoteAnalysis,
    )


def answer_project_question(
    text_generator: StructuredTextGenerator,
    question: str,
    notes: list[ChatNoteContext],
    history: list[ChatHistoryMessage],
) -> ChatAnswer:
    return text_generator.generate_structured(
        system_instruction=CHAT_SYSTEM_PROMPT,
        user_content=build_chat_prompt(question, notes, history),
        response_model=ChatAnswer,
    )
