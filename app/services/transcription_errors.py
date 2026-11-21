"""Transcription use-case failures without HTTP status codes."""


class AudioTooLarge(Exception):
    pass


class UnsupportedAudioType(Exception):
    pass


class InvalidAudio(Exception):
    pass


class TranscriptionUnavailable(Exception):
    pass
