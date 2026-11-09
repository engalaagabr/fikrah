"""HTTP request and response schemas for semantic search."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("Search query cannot be blank")
        return query


class SearchResult(BaseModel):
    note_id: UUID
    title: str | None
    content: str
    score: float
    updated_at: datetime
