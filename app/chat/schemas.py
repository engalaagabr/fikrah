"""HTTP request and response schemas for project knowledge chat."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message cannot be blank")
        return content


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class SourceView(BaseModel):
    note_id: UUID
    title: str | None


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    supported: bool | None
    sources: list[SourceView] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationView):
    messages: list[MessageView]


class MessageSubmission(BaseModel):
    conversation: ConversationView
    user_message: MessageView
    assistant_message: MessageView
