import pytest

from app.worker.config import WorkerSettings


def test_worker_settings_use_documented_safe_defaults() -> None:
    settings = WorkerSettings.from_env({})

    assert settings.max_retries == 3
    assert settings.retry_backoff_seconds == 5
    assert settings.stale_dispatch_after_seconds == 300
    assert settings.stale_processing_after_seconds == 900
    assert settings.dispatch_interval_seconds == 30
    assert settings.dispatch_batch_size == 100
    assert settings.broker_visibility_timeout_seconds == 3600


def test_worker_settings_read_environment_overrides() -> None:
    settings = WorkerSettings.from_env({
        "FIKRAH_CELERY_MAX_RETRIES": "5",
        "FIKRAH_CELERY_RETRY_BACKOFF_SECONDS": "8",
        "FIKRAH_CELERY_VISIBILITY_TIMEOUT_SECONDS": "7200",
        "FIKRAH_DISPATCH_STALE_AFTER_SECONDS": "240",
        "FIKRAH_PROCESSING_STALE_AFTER_SECONDS": "1200",
        "FIKRAH_DISPATCH_INTERVAL_SECONDS": "15",
        "FIKRAH_DISPATCH_BATCH_SIZE": "50",
    })

    assert settings.max_retries == 5
    assert settings.retry_backoff_seconds == 8
    assert settings.broker_visibility_timeout_seconds == 7200
    assert settings.stale_dispatch_after_seconds == 240
    assert settings.stale_processing_after_seconds == 1200
    assert settings.dispatch_interval_seconds == 15
    assert settings.dispatch_batch_size == 50


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_worker_settings_reject_invalid_positive_integer(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="FIKRAH_DISPATCH_BATCH_SIZE must be a positive integer"):
        WorkerSettings.from_env({"FIKRAH_DISPATCH_BATCH_SIZE": value})
