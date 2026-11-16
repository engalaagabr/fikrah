"""HTTP request and response schemas for project endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Project name cannot be blank")
        return name


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_general: bool
    created_at: datetime
