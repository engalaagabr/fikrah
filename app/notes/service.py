"""Note application use cases and processing lifecycle rules."""

import json
from dataclasses import asdict
from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChatMessageSource,
    Note,
    NoteConnection,
    NoteIdempotencyKey,
    NoteProcessingJob,
    Project,
    VectorCleanupRequest,
)
from app.notes.contracts import (
    NoteCreateCommand,
    NoteUpdateCommand,
    ProposalActionCommand,
)


class NoteServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NoteService:
    async def _owned_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID, *, lock: bool = False
    ) -> Note:
        query = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        if lock:
            query = query.with_for_update()
        note = await db.scalar(query)
        if note is None:
            raise NoteServiceError(404, "Note not found")
        return note

    async def _owned_project(
        self, db: AsyncSession, user_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> Project:
        query = select(Project).where(
            Project.id == project_id, Project.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        project = await db.scalar(query)
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
    ) -> Note:
        # Holding the project row lock serializes creation against project deletion.
        await self._owned_project(db, user_id, project_id, lock=True)
        fingerprint = self._request_fingerprint(body, project_id)
        previous = await db.scalar(
            select(NoteIdempotencyKey).where(
                NoteIdempotencyKey.user_id == user_id,
                NoteIdempotencyKey.key == idempotency_key,
            )
        )
        if previous is not None:
            return await self._replay_idempotent_note(db, previous, fingerprint)

        note = Note(
            user_id=user_id,
            project_id=project_id,
            title=body.title,
            content=body.content,
        )
        db.add(note)
        await db.flush()
        db.add(
            NoteProcessingJob(
                note_id=note.id,
                revision=note.revision,
                processing_generation=note.processing_generation,
            )
        )
        db.add(
            NoteIdempotencyKey(
                user_id=user_id,
                key=idempotency_key,
                request_hash=fingerprint,
                note_id=note.id,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            previous = await db.scalar(
                select(NoteIdempotencyKey).where(
                    NoteIdempotencyKey.user_id == user_id,
                    NoteIdempotencyKey.key == idempotency_key,
                )
            )
            if previous is None:
                raise
            return await self._replay_idempotent_note(db, previous, fingerprint)
        await db.refresh(note)
        return note

    @staticmethod
    async def _replay_idempotent_note(
        db: AsyncSession, previous: NoteIdempotencyKey, fingerprint: str
    ) -> Note:
        if previous.request_hash != fingerprint:
            raise NoteServiceError(
                409, "Idempotency-Key was used with a different request"
            )
        note = await db.get(Note, previous.note_id)
        if note is None:
            raise NoteServiceError(
                410, "The note created by this request no longer exists"
            )
        return note

    async def list_project_notes(
        self, db: AsyncSession, user_id: UUID, project_id: UUID
    ) -> list[Note]:
        await self._owned_project(db, user_id, project_id)
        result = await db.scalars(
            select(Note)
            .where(Note.user_id == user_id, Note.project_id == project_id)
            .order_by(Note.updated_at.desc(), Note.id)
        )
        return list(result)

    async def get_note(self, db: AsyncSession, user_id: UUID, note_id: UUID) -> Note:
        return await self._owned_note(db, user_id, note_id)

    async def update_note(
        self, db: AsyncSession, user_id: UUID, note_id: UUID, body: NoteUpdateCommand
    ) -> Note:
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
        await db.refresh(note)
        return note

    async def retry_processing(
        self, db: AsyncSession, user_id: UUID, note_id: UUID
    ) -> Note:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        note.processing_generation += 1
        note.processing_status = "queued"
        self._enqueue(db, note)
        await db.commit()
        await db.refresh(note)
        return note

    async def regenerate_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> Note:
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
        await db.refresh(note)
        return note

    async def accept_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> Note:
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
        await db.refresh(note)
        return note

    async def reject_refinement(
        self,
        db: AsyncSession,
        user_id: UUID,
        note_id: UUID,
        body: ProposalActionCommand,
    ) -> Note:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        if note.processing_generation != body.expected_processing_generation:
            raise NoteServiceError(409, "The note processing result has changed")
        note.refinement_proposal = None
        await db.commit()
        await db.refresh(note)
        return note

    async def delete_note(self, db: AsyncSession, user_id: UUID, note_id: UUID) -> None:
        note = await self._owned_note(db, user_id, note_id, lock=True)
        db.add(VectorCleanupRequest(note_id=note.id))
        await db.execute(
            delete(NoteConnection).where(
                (NoteConnection.source_note_id == note.id)
                | (NoteConnection.target_note_id == note.id)
            )
        )
        await db.execute(
            delete(ChatMessageSource).where(ChatMessageSource.note_id == note.id)
        )
        await db.execute(
            delete(NoteProcessingJob).where(NoteProcessingJob.note_id == note.id)
        )
        await db.delete(note)
        await db.commit()

    @staticmethod
    def _enqueue(db: AsyncSession, note: Note) -> None:
        db.add(
            NoteProcessingJob(
                note_id=note.id,
                revision=note.revision,
                processing_generation=note.processing_generation,
            )
        )
