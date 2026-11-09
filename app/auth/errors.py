"""Authentication use-case errors independent of the HTTP framework."""


class AuthServiceError(Exception):
    """A safe authentication failure that the presentation layer can translate."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.headers = headers
