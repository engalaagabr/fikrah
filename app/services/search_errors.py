"""Errors raised by search use cases."""


class SearchProjectNotFound(Exception):
    """Raised when the requested project is not owned by the caller."""
