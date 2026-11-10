"""Persistence operations for generated note connections."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Note, NoteConnection

MAX_CONNECTIONS_PER_NOTE = 10


def _normalized_concepts(concepts: list[str]) -> set[str]:
    return {concept.strip().casefold() for concept in concepts if concept.strip()}


def refresh_note_connections(session: Session, note: Note) -> None:
    """Replace a note's outgoing links with its strongest same-project matches."""
    own_concepts = _normalized_concepts(note.concepts)
    session.execute(
        delete(NoteConnection).where(NoteConnection.source_note_id == note.id)
    )
    if not own_concepts:
        return

    candidates = session.scalars(
        select(Note)
        .where(
            Note.id != note.id,
            Note.user_id == note.user_id,
            Note.project_id == note.project_id,
            Note.processing_status == "completed",
        )
        .order_by(Note.updated_at.desc(), Note.id)
    ).all()
    related = [
        (len(overlap), candidate)
        for candidate in candidates
        if (overlap := own_concepts & _normalized_concepts(candidate.concepts))
    ]
    related.sort(key=lambda item: -item[0])

    table = NoteConnection.__table__
    dialect = session.get_bind().dialect.name
    for _, candidate in related[:MAX_CONNECTIONS_PER_NOTE]:
        values = {"source_note_id": note.id, "target_note_id": candidate.id}
        if dialect == "postgresql":
            statement = (
                pg_insert(table)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["source_note_id", "target_note_id"]
                )
            )
            session.execute(statement)
        elif dialect == "sqlite":
            statement = (
                sqlite_insert(table)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["source_note_id", "target_note_id"]
                )
            )
            session.execute(statement)
        else:
            session.add(NoteConnection(**values))
