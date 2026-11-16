"""Validated application settings loaded from the existing environment."""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DATABASE_URL_ENV = "DATABASE_URL"


class Settings(BaseSettings):
    """Environment configuration with the repository's existing names/defaults."""

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    redis_url: str = Field(
        default="redis://localhost:6379/0", validation_alias="REDIS_URL"
    )

    fikrah_celery_max_retries: str = Field(
        default="3", validation_alias="FIKRAH_CELERY_MAX_RETRIES"
    )
    fikrah_celery_retry_backoff_seconds: str = Field(
        default="5", validation_alias="FIKRAH_CELERY_RETRY_BACKOFF_SECONDS"
    )
    fikrah_celery_visibility_timeout_seconds: str = Field(
        default="3600", validation_alias="FIKRAH_CELERY_VISIBILITY_TIMEOUT_SECONDS"
    )
    fikrah_dispatch_stale_after_seconds: str = Field(
        default="300", validation_alias="FIKRAH_DISPATCH_STALE_AFTER_SECONDS"
    )
    fikrah_processing_stale_after_seconds: str = Field(
        default="900", validation_alias="FIKRAH_PROCESSING_STALE_AFTER_SECONDS"
    )
    fikrah_dispatch_interval_seconds: str = Field(
        default="30", validation_alias="FIKRAH_DISPATCH_INTERVAL_SECONDS"
    )
    fikrah_dispatch_batch_size: str = Field(
        default="100", validation_alias="FIKRAH_DISPATCH_BATCH_SIZE"
    )

    qdrant_url: str | None = Field(default=None, validation_alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, validation_alias="QDRANT_API_KEY")
    qdrant_notes_collection: str = Field(
        default="fikrah-notes", validation_alias="QDRANT_NOTES_COLLECTION"
    )

    llm_text_provider: str = Field(default="", validation_alias="LLM_TEXT_PROVIDER")
    deepseek_api_key: str | None = Field(
        default=None, validation_alias="DEEPSEEK_API_KEY"
    )
    deepseek_text_model: str = Field(
        default="deepseek-flash", validation_alias="DEEPSEEK_TEXT_MODEL"
    )
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_text_model: str = Field(
        default="gemini-3.8-flash", validation_alias="GEMINI_TEXT_MODEL"
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", validation_alias="GEMINI_EMBEDDING_MODEL"
    )
    gemini_embedding_dimensions: str = Field(
        default="768", validation_alias="GEMINI_EMBEDDING_DIMENSIONS"
    )
    openrouter_api_key: str | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY"
    )
    openrouter_text_model: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        validation_alias="OPENROUTER_TEXT_MODEL",
    )

    fikrah_jwt_secret: str = Field(default="", validation_alias="FIKRAH_JWT_SECRET")
    google_client_id: str | None = Field(
        default=None, validation_alias="GOOGLE_CLIENT_ID"
    )

    email_action_base_url: str | None = Field(
        default=None, validation_alias="EMAIL_ACTION_BASE_URL"
    )
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: str = Field(default="587", validation_alias="SMTP_PORT")
    smtp_from: str | None = Field(default=None, validation_alias="SMTP_FROM")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_use_tls: str = Field(default="false", validation_alias="SMTP_USE_TLS")
    smtp_start_tls: str = Field(default="true", validation_alias="SMTP_START_TLS")


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    max_retries: int
    retry_backoff_seconds: int
    stale_dispatch_after_seconds: int
    stale_processing_after_seconds: int
    dispatch_interval_seconds: int
    dispatch_batch_size: int
    broker_visibility_timeout_seconds: int


def get_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Read current environment values; explicit mappings stay isolated in tests."""
    if environ is None:
        return Settings()

    values = {
        str(field.validation_alias): field.default
        for field in Settings.model_fields.values()
    }
    values.update(environ)
    return Settings(**values)


def get_worker_settings(
    environ: Mapping[str, str] | None = None,
) -> WorkerSettings:
    """Parse worker numeric settings at Celery startup, matching prior timing."""
    settings = get_settings(environ)

    def positive_int(name: str, raw_value: str) -> int:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if value < 1:
            raise ValueError(f"{name} must be a positive integer")
        return value

    return WorkerSettings(
        max_retries=positive_int(
            "FIKRAH_CELERY_MAX_RETRIES", settings.fikrah_celery_max_retries
        ),
        retry_backoff_seconds=positive_int(
            "FIKRAH_CELERY_RETRY_BACKOFF_SECONDS",
            settings.fikrah_celery_retry_backoff_seconds,
        ),
        stale_dispatch_after_seconds=positive_int(
            "FIKRAH_DISPATCH_STALE_AFTER_SECONDS",
            settings.fikrah_dispatch_stale_after_seconds,
        ),
        stale_processing_after_seconds=positive_int(
            "FIKRAH_PROCESSING_STALE_AFTER_SECONDS",
            settings.fikrah_processing_stale_after_seconds,
        ),
        dispatch_interval_seconds=positive_int(
            "FIKRAH_DISPATCH_INTERVAL_SECONDS",
            settings.fikrah_dispatch_interval_seconds,
        ),
        dispatch_batch_size=positive_int(
            "FIKRAH_DISPATCH_BATCH_SIZE", settings.fikrah_dispatch_batch_size
        ),
        broker_visibility_timeout_seconds=positive_int(
            "FIKRAH_CELERY_VISIBILITY_TIMEOUT_SECONDS",
            settings.fikrah_celery_visibility_timeout_seconds,
        ),
    )
