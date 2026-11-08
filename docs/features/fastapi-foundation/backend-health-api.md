# Feature: FastAPI Foundation and Health Endpoint

## Purpose

Provide a minimal FastAPI application entry point and a health endpoint for checking whether the Backend process is running.

## Run Locally

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

FastAPI's interactive API documentation is available at `/docs` while the local server is running.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Endpoint Contract

### `GET /health`

- **What it does:** Reports that the API process is running.
- **Why the mobile application or operations tooling needs it:** It provides a lightweight way to check API availability before diagnosing product requests.
- **When it is called:** During local development or by operational health checks.
- **Request information:** No request body or parameters.
- **Response information:** HTTP 200 with `{ "status": "ok" }`.
- **Authentication:** None for this minimal operational endpoint.

## Decisions Kept Open

PostgreSQL and Qdrant have been selected for the project, but this foundation does not implement either store. The authentication provider, deployment platform, and AI provider remain open for discussion.
