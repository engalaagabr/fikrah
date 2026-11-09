"""Project use cases and project lifecycle rules."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.projects.repository import ProjectRepository


class ProjectNotFound(Exception):
    pass


class GeneralProjectProtected(Exception):
    pass


class ProjectService:
    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self._repository = repository or ProjectRepository()

    async def list_projects(self, db: AsyncSession, user_id: UUID) -> list[Project]:
        return await self._repository.list_for_user(db, user_id)

    async def create_project(
        self, db: AsyncSession, user_id: UUID, name: str
    ) -> Project:
        return await self._repository.create(db, user_id, name)

    async def get_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> Project:
        project = await self._repository.find_owned(db, user_id, project_id)
        if project is None:
            raise ProjectNotFound
        return project

    async def rename_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, name: str
    ) -> Project:
        project = await self._repository.find_owned(db, user_id, project_id)
        if project is None:
            raise ProjectNotFound
        project.name = name
        return await self._repository.save(db, project)

    async def delete_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> None:
        project = await self._repository.find_owned(db, user_id, project_id, lock=True)
        if project is None:
            raise ProjectNotFound
        if project.is_general:
            raise GeneralProjectProtected
        await self._repository.delete_with_owned_data(db, project)
