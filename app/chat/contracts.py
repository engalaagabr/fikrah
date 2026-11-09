"""Framework-independent commands and results for project chat use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConversationCreateCommand:
    title: str | None = None


@dataclass(frozen=True, slots=True)
class MessageCreateCommand:
    content: str


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    id: UUID
    project_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SourceReference:
    note_id: UUID
    title: str | None


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: UUID
    role: str
    content: str
    supported: bool | None
    sources: tuple[SourceReference, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationHistory:
    conversation: ConversationSummary
    messages: tuple[MessageRecord, ...]


@dataclass(frozen=True, slots=True)
class MessageSubmissionResult:
    conversation: ConversationSummary
    user_message: MessageRecord
    assistant_message: MessageRecord
