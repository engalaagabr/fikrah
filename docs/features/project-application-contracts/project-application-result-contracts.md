# Project Application Result Contracts

## Goal

Keep project use cases independent from FastAPI response schemas and prevent SQLAlchemy project records from crossing into the HTTP layer.

## Design

- `app/services/contracts/projects.py` defines the immutable `ProjectResult` returned by project application use cases.
- `ProjectService` maps repository results to `ProjectResult` for list, create, read, and rename operations.
- `app/api/v1/projects.py` maps `ProjectResult` values to the public `ProjectView` schema.
- Project deletion behavior and repository persistence operations remain unchanged.

## API Impact

There is no API contract or database schema change. Existing routes retain the same request and response fields, status codes, and ownership behavior.
