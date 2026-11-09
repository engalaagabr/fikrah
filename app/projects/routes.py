"""CRUD endpoints for a user's projects."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.routes import current_user
from app.database import get_db_session
from app.models import Note, NoteConnection, NoteProcessingJob, Project, User, VectorCleanupRequest

router = APIRouter(prefix="/v1/projects", tags=["projects"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


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


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("", response_model=list[ProjectView])
async def list_projects(user: AuthenticatedUser, db: Db) -> list[ProjectView]:
    projects = await db.scalars(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.is_general.desc(), Project.created_at, Project.id)
    )
    return [ProjectView.model_validate(project) for project in projects]


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectInput, user: AuthenticatedUser, db: Db) -> ProjectView:
    project = Project(user_id=user.id, name=body.name, is_general=False)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectView.model_validate(project)


@router.get("/{project_id}", response_model=ProjectView)
async def get_project(project_id: UUID, user: AuthenticatedUser, db: Db) -> ProjectView:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise _not_found()
    return ProjectView.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectView)
async def rename_project(
    project_id: UUID, body: ProjectInput, user: AuthenticatedUser, db: Db
) -> ProjectView:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise _not_found()
    project.name = body.name
    await db.commit()
    await db.refresh(project)
    return ProjectView.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, user: AuthenticatedUser, db: Db) -> Response:
    project = await db.scalar(
        select(Project)
        .where(Project.id == project_id, Project.user_id == user.id)
        .with_for_update()
    )
    if project is None:
        raise _not_found()
    if project.is_general:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The General project cannot be deleted")
    note_ids = list(await db.scalars(select(Note.id).where(Note.project_id == project.id)))
    db.add_all(VectorCleanupRequest(note_id=note_id) for note_id in note_ids)
    if note_ids:
        await db.execute(
            delete(NoteConnection).where(
                NoteConnection.source_note_id.in_(note_ids) | NoteConnection.target_note_id.in_(note_ids)
            )
        )
        await db.execute(delete(NoteProcessingJob).where(NoteProcessingJob.note_id.in_(note_ids)))
        await db.execute(delete(Note).where(Note.id.in_(note_ids)))
    await db.delete(project)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
