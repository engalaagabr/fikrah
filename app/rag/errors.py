"""Failures raised by retrieval infrastructure adapters."""


class SearchUnavailableError(RuntimeError):
    """Raised when semantic retrieval cannot reach an embedding/vector service."""
