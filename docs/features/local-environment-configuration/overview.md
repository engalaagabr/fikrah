# Local Environment Configuration

## Purpose

Load developer-specific settings from a root `.env` file for both the FastAPI
application and Celery worker. The file is ignored by Git, and process-level
environment variables take precedence over values in the file.

## Setup

Copy `.env.example` to `.env` in the repository root. Set local PostgreSQL,
Redis, and Qdrant URLs, then add provider credentials when AI-backed processing
is needed. `.env.example` contains placeholders only; the workspace `.env` may
contain private values and must not be committed.

## Loading behavior

Importing the `app` package loads `<repository-root>/.env` without replacing
environment variables already configured by the host process. This covers both
`uvicorn app.main:app` and `celery -A app.worker.celery_app worker` entry points.

## Local defaults and required integrations

- PostgreSQL, Redis, and Qdrant URLs point to local services by default.
- `FIKRAH_JWT_SECRET` must be a private key of at least 32 characters.
- DeepSeek and Gemini API keys are blank until supplied by the developer.
- Google OAuth and SMTP settings are optional until those flows are exercised.
- Email action links must use an HTTPS URL accepted by the mobile application.
