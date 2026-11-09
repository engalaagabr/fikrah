"""Validated environment settings for durable worker dispatch and retries."""

from dataclasses import dataclass
import os
from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    max_retries: int
    retry_backoff_seconds: int
    stale_dispatch_after_seconds: int
    stale_processing_after_seconds: int
    dispatch_interval_seconds: int
    dispatch_batch_size: int
    broker_visibility_timeout_seconds: int

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "WorkerSettings":
        source = os.environ if environ is None else environ

        def positive_int(name: str, default: int) -> int:
            raw_value = source.get(name, str(default))
            try:
                value = int(raw_value)
            except ValueError as exc:
                raise ValueError(f"{name} must be a positive integer") from exc
            if value < 1:
                raise ValueError(f"{name} must be a positive integer")
            return value

        return cls(
            max_retries=positive_int("FIKRAH_CELERY_MAX_RETRIES", 3),
            retry_backoff_seconds=positive_int("FIKRAH_CELERY_RETRY_BACKOFF_SECONDS", 5),
            stale_dispatch_after_seconds=positive_int("FIKRAH_DISPATCH_STALE_AFTER_SECONDS", 300),
            stale_processing_after_seconds=positive_int("FIKRAH_PROCESSING_STALE_AFTER_SECONDS", 900),
            dispatch_interval_seconds=positive_int("FIKRAH_DISPATCH_INTERVAL_SECONDS", 30),
            dispatch_batch_size=positive_int("FIKRAH_DISPATCH_BATCH_SIZE", 100),
            broker_visibility_timeout_seconds=positive_int("FIKRAH_CELERY_VISIBILITY_TIMEOUT_SECONDS", 3600),
        )
