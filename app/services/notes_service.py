"""Note application use cases and processing lifecycle rules."""

import json
from dataclasses import asdict
from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.note_results import NoteResult
from app.contracts.notes import (
    NoteCreateCommand,
    NoteUpdateCommand,
    ProposalActionCommand,
    ProposalUpdateCommand,
)
from app.models import (
    Note,
    NoteIdempotencyKey,
    Project,
)
from app.repositories.notes import NoteRepository


class NoteServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NoteService:
    def __init__(self, repository: NoteRepository | None = None) -> None:
        self._repository = repository or NoteRepository()

    async def _owned_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID, *, lock: bool = False
    ) -> Note:
        note = await self._repository.find_owned_note(
            db, user_id, note_id, lock=lock
        )
        if note is None:
            raise NoteServiceError(404, "Note not found")
        return note

    async def _owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project:
        project = await self._repository.find_owned_project(
            db, user_id, project_id, lock=lock
        )
        if project is None:
            raise NoteServiceError(404, "Project not found")
        return project

    @staticmethod
    def _request_fingerprint(body: NoteCreateCommand, project_id: UUID) -> str:
        payload = {"project_id": str(project_id), **asdict(body)}
        stable_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(stable_body.encode()).hexdigest()

    async def create_note(
        self,
        db: AsyncSession,
        user_id: UUID,
        project_id: UUID,
        body: NoteCreateCommand,
        idempotency_key: str,
    ) -> NoteResult:
        # Holding the project row lock serializes creation against project deletion.
        await self._owned_project(db, user_id, project_id, lock=True)
        fingerprint = self._request_fingerprint(body, project_id)
        previous = await self._repository.find_idempotency_key(
            db, user_id, idempotency_key
        )
        if previous is not None:
            note = await self._replay_idempotent_note(db, previous, fingerprint)
            return self._result(note)

        note = Note(
            user_id=user_id,
            project_id=project_id,
            title=body.title,
            content=body.content,
        )
        await self._repository.add_note(db, note)
        self._repository.enqueue_processing(db, note)
        self._repository.add_idempotency_key(
            db,
            NoteIdempotencyKey(
                user_id=user_id,
                key=idempotency_key,
                request_hash=fingerprint,
                note_id=note.id,
            ),
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            previous = await self._repository.find_idempotency_key(
                db, user_id, idempotency_key
            )
            if previous is None:
                raise
            note = await self._replay_idempotent_note(db, previous, fingerprint)
            return self._result(note)
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def _replay_idempotent_note(
        self, db: AsyncSession, previous: NoteIdempotencyKey, fingerprint: str
    ) -> Note:
        if previous.request_hash != fingerprint:
            raise NoteServiceError(
                409, "Idempotency-Key was used with a different request"
            )
        note = await self._repository.get_note(db, previous.note_id)
        if note is None:
            raise NoteServiceError(
                410, "The note created by this request no longer exists"
            )
        return note

    async def list_project_notes(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[NoteResult]:
        await self._owned_project(db, user_id, project_id)
        notes = await self._repository.list_for_project(db, user_id, project_id)
        return [self._result(note) for note in notes]

    async def get_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id)
        return self._result(note)

    async def update_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID, body: NoteUpdateCommand
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if "content" in body.provided_fields:
            if body.content is None:
                raise NoteServiceError(422, "Note content cannot be null")
            note.content = body.content
            note.refinement_proposal = None
        if "title" in body.provided_fields:
            note.title = body.title
        note.revision += 1
        note.processing_generation += 1
        note.processing_status = "queued"
        self._enqueue(db, note)
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def retry_processing(
        self, db: AsyncSession, user_id: UUID, note_id: UUID
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_status in {"queued", "processing"}:
            return self._result(note)
        note.processing_generation += 1
        note.processing_status = "queued"
        self._enqueue(db, note)
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def regenerate_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_generation != body.expected_processing_generation:
            raise NoteServiceError(409, "The note processing result has changed")
        if note.processing_status != "completed":
            raise NoteServiceError(
                409, "The note must finish processing before regenerating its proposal"
            )
        note.processing_generation += 1
        note.refinement_proposal = None
        note.processing_status = "queued"
        self._enqueue(db, note)
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def accept_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_generation != body.expected_processing_generation:
            raise NoteServiceError(409, "The note processing result has changed")
        if note.processing_status != "completed" or note.refinement_proposal is None:
            raise NoteServiceError(409, "No completed refinement proposal is available")
        note.content = note.refinement_proposal
        note.refinement_proposal = None
        note.revision += 1
        note.processing_generation += 1
        note.processing_status = "queued"
        self._enqueue(db, note)
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def update_refinement_proposal(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalUpdateCommand,
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_generation != body.expected_processing_generation:
            raise NoteServiceError(409, "The note processing result has changed")
        if note.processing_status != "completed" or note.refinement_proposal is None:
            raise NoteServiceError(409, "No completed refinement proposal is available")
        note.refinement_proposal = body.refinement_proposal
        note.processing_generation += 1
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def reject_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> NoteResult:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_generation != body.expected_processing_generation:
            raise NoteServiceError(409, "The note processing result has changed")
        note.refinement_proposal = None
        await db.commit()
        await self._repository.refresh_note(db, note)
        return self._result(note)

    async def delete_note(self, db: AsyncSession, user_id: UUID, note_id: UUID) -> None:
        note = await self._owned_note(db, user_id, note_id)
        await self._repository.lock_project_processing(db, note.project_id)
        note = await self._owned_note(db, user_id, note_id, lock=True)
        await self._repository.delete_with_owned_data(db, note)
        await db.commit()

    @staticmethod
    def _result(note: Note) -> NoteResult:
        return NoteResult(
            id=note.id,
            project_id=note.project_id,
            title=note.title,
            content=note.content,
            concepts=tuple(note.concepts or ()),
            refinement_proposal=note.refinement_proposal,
            revision=note.revision,
            processing_generation=note.processing_generation,
            processing_status=note.processing_status,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    def _enqueue(self, db: AsyncSession, note: Note) -> None:
        self._repository.enqueue_processing(db, note)
