"""Provider failures that do not expose HTTP clients or upstream response bodies."""


class AudioRejectedError(Exception):
    """The transcription provider could not process the supplied audio."""


class TranscriptionUnavailableError(Exception):
    """A complete transcription could not be obtained from the provider."""
