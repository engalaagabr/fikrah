"""Project-level coordination shared by API deletion and worker persistence."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_PROCESSING_LOCK = text(
    "SELECT pg_advisory_xact_lock(hashtextextended(:project_id, 0))"
)


async def lock_project_processing(db: AsyncSession, project_id: UUID) -> None:
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(PROJECT_PROCESSING_LOCK, {"project_id": str(project_id)})
