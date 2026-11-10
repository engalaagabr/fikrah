"""Framework-independent results for project use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProjectResult:
    id: UUID
    name: str
    is_general: bool
    created_at: datetime
