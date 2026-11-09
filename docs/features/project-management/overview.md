# Project Management API

## Status

The user approved the project collection and resource routes under `/v1/projects`. This feature implements authenticated list, create, retrieve, rename, and delete operations.

## User Behavior

- Projects belong to the authenticated account; clients do not send an owner ID.
- Every account already has its protected `General` project.
- The API returns `General` first in project lists.
- Project names are trimmed and limited to 120 characters. Duplicate names are allowed.
- A project can be renamed while retaining its project identity and `is_general` role. The `General` project cannot be deleted.
- Requests for another user's project return the same `404` as an unknown project ID.

## API Contract

All routes require `Authorization: Bearer <access_token>`.

| Endpoint | Purpose and call timing | Request | Response |
| --- | --- | --- | --- |
| `GET /v1/projects` | Load the signed-in user's projects on startup and after project changes. | None. | Array of `{ id, name, is_general, created_at }`, with General first. |
| `POST /v1/projects` | Create a project from the project-creation flow. | `{ "name": "Research" }` | `201` with the created project. |
| `GET /v1/projects/{project_id}` | Read project details when opening a project. | Project ID in path. | Project object or `404`. |
| `PATCH /v1/projects/{project_id}` | Save a project rename. | `{ "name": "New name" }` | Updated project object or `404`. |
| `DELETE /v1/projects/{project_id}` | Delete a project after user confirmation. | Project ID in path. | `204`; `409` when attempting to delete General; `404` for another user's or unknown project. |

## Persistence and Scope

The existing `projects` table stores `user_id`, `name`, and `is_general`. Each lookup filters by both the requested project ID and the authenticated user ID. Project deletion relies on PostgreSQL foreign-key cascades for future project-owned relational records.

Deleting a project removes its relational notes, note connections, and queued processing jobs in the same PostgreSQL transaction. It also writes one durable vector-cleanup request for each deleted note; Qdrant deletion is asynchronous and will be performed by the worker feature. The protected General project cannot be deleted.

## Verification

API tests cover list/create/read/rename/delete, General deletion protection, authentication, validation, and cross-user access isolation.
