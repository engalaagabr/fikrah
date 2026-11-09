"""Errors shared by the search use case and its infrastructure adapters."""


class SearchUnavailableError(RuntimeError):
    """Raised when semantic retrieval cannot reach an embedding/vector service."""
