"""HTTP presentation layer for project endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import AuthenticatedUser, Db
from app.infrastructure.container import project_service
from app.schemas.projects import ProjectInput, ProjectView
from app.services.contracts.projects import ProjectResult
from app.services.projects_service import (
    GeneralProjectProtected,
    ProjectNotFound,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _translate_service_error(error: Exception) -> HTTPException:
    if isinstance(error, ProjectNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if isinstance(error, GeneralProjectProtected):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The General project cannot be deleted",
        )
    raise error


def _project_view(project: ProjectResult) -> ProjectView:
    return ProjectView(
        id=project.id,
        name=project.name,
        is_general=project.is_general,
        created_at=project.created_at,
    )


@router.get("", response_model=list[ProjectView])
async def list_projects(user: AuthenticatedUser, db: Db) -> list[ProjectView]:
    projects = await project_service.list_projects(db, user.id)
    return [_project_view(project) for project in projects]


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectInput, user: AuthenticatedUser, db: Db
) -> ProjectView:
    project = await project_service.create_project(db, user.id, body.name)
    return _project_view(project)


@router.get("/{project_id}", response_model=ProjectView)
async def get_project(project_id: UUID, user: AuthenticatedUser, db: Db) -> ProjectView:
    try:
        project = await project_service.get_project(db, user.id, project_id)
    except ProjectNotFound as error:
        raise _translate_service_error(error) from error
    return _project_view(project)


@router.patch("/{project_id}", response_model=ProjectView)
async def rename_project(
    project_id: UUID, body: ProjectInput, user: AuthenticatedUser, db: Db
) -> ProjectView:
    try:
        project = await project_service.rename_project(
            db, user.id, project_id, body.name
        )
    except ProjectNotFound as error:
        raise _translate_service_error(error) from error
    return _project_view(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, user: AuthenticatedUser, db: Db) -> Response:
    try:
        await project_service.delete_project(db, user.id, project_id)
    except (ProjectNotFound, GeneralProjectProtected) as error:
        raise _translate_service_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
