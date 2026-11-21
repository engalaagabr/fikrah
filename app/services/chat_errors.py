"""Chat workflow failures, independent of their HTTP representation."""

from enum import StrEnum


class ChatFailure(StrEnum):
    PROJECT_NOT_FOUND = "project_not_found"
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"
    GENERATION_UNAVAILABLE = "generation_unavailable"
    CONVERSATION_CHANGED = "conversation_changed"
    INVALID_MODEL_RESPONSE = "invalid_model_response"


class ChatServiceError(Exception):
    def __init__(self, code: ChatFailure, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
