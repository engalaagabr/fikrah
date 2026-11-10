"""HTTP presentation layer for note endpoints."""

from collections.abc import Awaitable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.database import get_db_session
from app.models import User
from app.notes.contracts import (
    NoteCreateCommand,
    NoteUpdateCommand,
    ProposalActionCommand,
)
from app.notes.results import NoteResult
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
        raise HTTPException(
            status_code=error.status_code, detail=error.detail
        ) from error


def _note_view(note: NoteResult) -> NoteView:
    return NoteView(
        id=note.id,
        project_id=note.project_id,
        title=note.title,
        content=note.content,
        concepts=list(note.concepts),
        refinement_proposal=note.refinement_proposal,
        revision=note.revision,
        processing_generation=note.processing_generation,
        processing_status=note.processing_status,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


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
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
) -> NoteView:
    note = await _execute(
        note_service.create_note(
            db,
            user.id,
            project_id,
            NoteCreateCommand(content=body.content, title=body.title),
            idempotency_key,
        )
    )
    return _note_view(note)


@router.get("/v1/projects/{project_id}/notes", response_model=list[NoteView])
async def list_project_notes(
    project_id: UUID, user: AuthenticatedUser, db: Db
) -> list[NoteView]:
    notes = await _execute(note_service.list_project_notes(db, user.id, project_id))
    return [_note_view(note) for note in notes]


@router.get("/v1/notes/{note_id}", response_model=NoteView)
async def get_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> NoteView:
    note = await _execute(note_service.get_note(db, user.id, note_id))
    return _note_view(note)


@router.patch("/v1/notes/{note_id}", response_model=NoteView)
async def update_note(
    note_id: UUID, body: NoteUpdate, user: AuthenticatedUser, db: Db
) -> NoteView:
    command = NoteUpdateCommand(
        content=body.content,
        title=body.title,
        provided_fields=frozenset(body.model_fields_set),
    )
    note = await _execute(note_service.update_note(db, user.id, note_id, command))
    return _note_view(note)


@router.post(
    "/v1/notes/{note_id}/processing-retries",
    response_model=NoteView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_note_processing(
    note_id: UUID, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(note_service.retry_processing(db, user.id, note_id))
    return _note_view(note)


@router.post(
    "/v1/notes/{note_id}/refinement-regenerations",
    response_model=NoteView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(
        note_service.regenerate_refinement(
            db,
            user.id,
            note_id,
            ProposalActionCommand(
                expected_processing_generation=body.expected_processing_generation
            ),
        )
    )
    return _note_view(note)


@router.post("/v1/notes/{note_id}/refinement-acceptance", response_model=NoteView)
async def accept_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(
        note_service.accept_refinement(
            db,
            user.id,
            note_id,
            ProposalActionCommand(
                expected_processing_generation=body.expected_processing_generation
            ),
        )
    )
    return _note_view(note)


@router.post("/v1/notes/{note_id}/refinement-rejections", response_model=NoteView)
async def reject_refinement(
    note_id: UUID, body: ProposalAction, user: AuthenticatedUser, db: Db
) -> NoteView:
    note = await _execute(
        note_service.reject_refinement(
            db,
            user.id,
            note_id,
            ProposalActionCommand(
                expected_processing_generation=body.expected_processing_generation
            ),
        )
    )
    return _note_view(note)


@router.delete("/v1/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: UUID, user: AuthenticatedUser, db: Db) -> Response:
    await _execute(note_service.delete_note(db, user.id, note_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
