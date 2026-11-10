"""Framework-independent commands for note application use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NoteCreateCommand:
    content: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class NoteUpdateCommand:
    content: str | None
    title: str | None
    provided_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class ProposalActionCommand:
    expected_processing_generation: int


@dataclass(frozen=True, slots=True)
class ProposalUpdateCommand:
    expected_processing_generation: int
    refinement_proposal: str
