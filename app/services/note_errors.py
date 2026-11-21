"""Note workflow failures, independent of their HTTP representation."""

from enum import StrEnum


class NoteFailure(StrEnum):
    NOTE_NOT_FOUND = "note_not_found"
    PROJECT_NOT_FOUND = "project_not_found"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    NOTE_DELETED = "note_deleted"
    EMPTY_CONTENT = "empty_content"
    STALE_PROCESSING_RESULT = "stale_processing_result"
    PROCESSING_INCOMPLETE = "processing_incomplete"
    PROPOSAL_UNAVAILABLE = "proposal_unavailable"


class NoteServiceError(Exception):
    def __init__(self, code: NoteFailure, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
