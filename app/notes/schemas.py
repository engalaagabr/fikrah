"""HTTP request and response schemas for note endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NoteCreate(BaseModel):
    content: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=240)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Note content cannot be blank")
        return content

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        return title or None


class NoteUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, max_length=240)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        content = value.strip()
        if not content:
            raise ValueError("Note content cannot be blank")
        return content

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        return title or None

    @model_validator(mode="after")
    def require_a_change(self) -> "NoteUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one of content or title is required")
        return self


class ProposalAction(BaseModel):
    expected_processing_generation: int = Field(ge=1)


class ProposalUpdate(ProposalAction):
    refinement_proposal: str = Field(min_length=1)

    @field_validator("refinement_proposal")
    @classmethod
    def validate_refinement_proposal(cls, value: str) -> str:
        proposal = value.strip()
        if not proposal:
            raise ValueError("Refinement proposal cannot be blank")
        return proposal


class NoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    content: str
    concepts: list[str]
    refinement_proposal: str | None
    revision: int
    processing_generation: int
    processing_status: str
    created_at: datetime
    updated_at: datetime
