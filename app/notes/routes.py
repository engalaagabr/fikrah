"""CRUD and processing lifecycle endpoints for user notes."""

from hashlib import sha256
import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.routes import current_user
from app.database import get_db_session
from app.models import (
    Note,
    NoteConnection,
    NoteIdempotencyKey,
    NoteProcessingJob,
    Project,
    User,
    VectorCleanupRequest,
)

router = APIRouter(tags=["notes"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]


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


class NoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    content: str
    concepts: list[str]
    refinement_proposal: str | None
    revision: int
    processing_status: str
    created_at: datetime
    updated_at: datetime


def _note_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Note not found")


async def _owned_note(db: AsyncSession, user_id: UUID, note_id: UUID) -> Note:
    note = await db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user_id))
    if note is None:
        raise _note_not_found()
    return note


async def _owned_project(db: AsyncSession, user_id: UUID, project_id: UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _request_fingerprint(body: NoteCreate, project_id: UUID) -> str:
    payload = {"project_id": str(project_id), **body.model_dump(mode="json")}
    stable_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(stable_body.encode()).hexdigest()


@router.post(
    "/v1/projects/{project_id}/notes",
    response_model=NoteView,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    project_id: UUID,
    body: NoteCreate,
    user: AuthenticatedUser,
    db: Db,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> NoteView:
    await _owned_project(db, user.id, project_id)
    fingerprint = _request_fingerprint(body, project_id)
    previous = await db.scalar(
        select(NoteIdempotencyKey).where(
            NoteIdempotencyKey.user_id == user.id, NoteIdempotencyKey.key == idempotency_key
        )
    )
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key was used with a different request")
        note = await db.get(Note, previous.note_id)
        if note is None:
            raise HTTPException(status_code=410, detail="The note created by this request no longer exists")
        return NoteView.model_validate(note)

    note = Note(user_id=user.id, project_id=project_id, title=body.title, content=body.content)
    db.add(note)
    await db.flush()
    db.add(NoteProcessingJob(note_id=note.id, revision=note.revision))
    db.add(NoteIdempotencyKey(
        user_id=user.id,
        key=idempotency_key,
        request_hash=fingerprint,
        note_id=note.id,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        previous = await db.scalar(
            select(NoteIdempotencyKey).where(
                NoteIdempotencyKey.user_id == user.id, NoteIdempotencyKey.key == idempotency_key
            )
        )
        if previous is None:
            raise
        if previous.request_hash != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key was used with a different request")
        note = await db.get(Note, previous.note_id)
        if note is None:
            raise HTTPException(status_code=410, detail="The note created by this request no longer exists")
        return NoteView.model_validate(note)
    await db.refresh(note)
    return NoteView.model_validate(note)


@router.get("/v1/projects/{project_id}/notes", response_model=list[NoteView])
async def list_project_notes(project_id: UUID, user: AuthenticatedUser, db: Db) -> list[NoteView]:
    await _owned_project(db, user.id, project_id)
    notes = await db.scalars(
        select(Note)
        .where(Note.user_id == user.id, Note.project_id == project_id)
        .order_by(Note.updated_at.desc(), Note.id)
    )
    return [NoteView.model_validate(note) for note in notes]


@router.get("/v1/notes/{note_id}", response_model=NoteView)
async def get_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> NoteView:
    return NoteView.model_validate(await _owned_note(db, user.id, note_id))


@router.patch("/v1/notes/{note_id}", response_model=NoteView)
async def update_note(note_id: UUID, body: NoteUpdate, user: AuthenticatedUser, db: Db) -> NoteView:
    note = await _owned_note(db, user.id, note_id)
    if "content" in body.model_fields_set:
        if body.content is None:
            raise HTTPException(status_code=422, detail="Note content cannot be null")
        note.content = body.content
    if "title" in body.model_fields_set:
        note.title = body.title
    note.revision += 1
    note.processing_status = "queued"
    db.add(NoteProcessingJob(note_id=note.id, revision=note.revision))
    await db.commit()
    await db.refresh(note)
    return NoteView.model_validate(note)


@router.post("/v1/notes/{note_id}/processing-retries", response_model=NoteView, status_code=202)
async def retry_note_processing(note_id: UUID, user: AuthenticatedUser, db: Db) -> NoteView:
    note = await _owned_note(db, user.id, note_id)
    note.processing_status = "queued"
    db.add(NoteProcessingJob(note_id=note.id, revision=note.revision))
    await db.commit()
    await db.refresh(note)
    return NoteView.model_validate(note)


@router.delete("/v1/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> Response:
    note = await _owned_note(db, user.id, note_id)
    db.add(VectorCleanupRequest(note_id=note.id))
    await db.execute(
        delete(NoteConnection).where(
            (NoteConnection.source_note_id == note.id) | (NoteConnection.target_note_id == note.id)
        )
    )
    await db.execute(delete(NoteProcessingJob).where(NoteProcessingJob.note_id == note.id))
    await db.delete(note)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
