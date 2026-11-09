"""HTTP presentation layer for note endpoints."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.database import get_db_session
from app.models import User
from app.notes.schemas import NoteCreate, NoteUpdate, NoteView, ProposalAction
from app.notes.service import NoteService, NoteServiceError

router = APIRouter(tags=["notes"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
AuthenticatedUser = Annotated[User, Depends(current_user)]
note_service = NoteService()
T = TypeVar("T")


async def _execute(call: Awaitable[T]) -> T:
    try:
        return await call
    except NoteServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


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
    note = await _execute(
        note_service.create_note(db, user.id, project_id, body, idempotency_key)
    )
    return NoteView.model_validate(note)


@router.get("/v1/projects/{project_id}/notes", response_model=list[NoteView])
async def list_project_notes(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> list[NoteView]:
    notes = await _execute(note_service.list_project_notes(db, user.id, project_id))
    return [NoteView.model_validate(note) for note in notes]


@router.get("/v1/notes/{note_id}", response_model=NoteView)
async def get_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> NoteView:
    note = await _execute(note_service.get_note(db, user.id, note_id))
    return NoteView.model_validate(note)


@router.patch("/v1/notes/{note_id}", response_model=NoteView)
async def update_note(
    note_id: UUID, body: NoteUpdate, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(note_service.update_note(db, user.id, note_id, body))
    return NoteView.model_validate(note)


@router.post(
    "/v1/notes/{note_id}/processing-retries",
    response_model=NoteView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_note_processing(
    note_id: UUID, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(note_service.retry_processing(db, user.id, note_id))
    return NoteView.model_validate(note)


@router.post(
    "/v1/notes/{note_id}/refinement-regenerations",
    response_model=NoteView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(
        note_service.regenerate_refinement(db, user.id, note_id, body)
    )
    return NoteView.model_validate(note)


@router.post("/v1/notes/{note_id}/refinement-acceptance", response_model=NoteView)
async def accept_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(note_service.accept_refinement(db, user.id, note_id, body))
    return NoteView.model_validate(note)


@router.post("/v1/notes/{note_id}/refinement-rejections", response_model=NoteView)
async def reject_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(note_service.reject_refinement(db, user.id, note_id, body))
    return NoteView.model_validate(note)


@router.delete("/v1/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> Response:
    await _execute(note_service.delete_note(db, user.id, note_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
