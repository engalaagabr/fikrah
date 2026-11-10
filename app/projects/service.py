"""Project use cases and project lifecycle rules."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.projects.contracts import ProjectResult
from app.projects.repository import ProjectRepository


class ProjectNotFound(Exception):
    pass


class GeneralProjectProtected(Exception):
    pass


class ProjectService:
    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self._repository = repository or ProjectRepository()

    async def list_projects(
        self, db: AsyncSession, user_id: UUID
    ) -> list[ProjectResult]:
        projects = await self._repository.list_for_user(db, user_id)
        return [self._result(project) for project in projects]

    async def create_project(
        self, db: AsyncSession, user_id: UUID, name: str
    ) -> ProjectResult:
        project = await self._repository.create(db, user_id, name)
        return self._result(project)

    async def get_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> ProjectResult:
        project = await self._repository.find_owned(db, user_id, project_id)
        if project is None:
            raise ProjectNotFound
        return self._result(project)

    async def rename_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, name: str
    ) -> ProjectResult:
        project = await self._repository.find_owned(db, user_id, project_id)
        if project is None:
            raise ProjectNotFound
        project.name = name
        project = await self._repository.save(db, project)
        return self._result(project)

    async def delete_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> None:
        project = await self._repository.find_owned(db, user_id, project_id, lock=True)
        if project is None:
            raise ProjectNotFound
        if project.is_general:
            raise GeneralProjectProtected
        await self._repository.delete_with_owned_data(db, project)

    @staticmethod
    def _result(project: Project) -> ProjectResult:
        return ProjectResult(
            id=project.id,
            name=project.name,
            is_general=project.is_general,
            created_at=project.created_at,
        )
