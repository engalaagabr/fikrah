# Security and Reliability Remediation

This phase addresses the architecture/security review of commit `0975d0f`. Fixes are made in small steps with regression coverage. Existing migration versions and local `.env` are preserved.

| Finding | Status |
| --- | --- |
| F01: unverified password survives Google linking | Fixed; regression verifies the old password and pending action links cannot be used after linking. Already verified passwords remain usable. |
| F02: non-authoritative Google email linking | Policy approved; implementation pending. |
| F03/F04: login, request, and content budgets | Proposed limits approved; implementation pending. |
| F05: worker attempt ownership | Fixed; unique attempt tokens fence completion and failure, and retries release only their own claim. |
| F06: worker lock order | Fixed; note locks precede job locks, dispatcher skips locked notes, and deletion shares project coordination with graph/vector completion. Two real PostgreSQL regressions pass. |
| F07: answers retain invalidated evidence | Pending. |
| F08: accepted public JWT placeholder | Fixed; startup and token operations reject the tracked public placeholder and missing/short secrets. |
| F09/F10: access-token invalidation and refresh replay | Policy approved; implementation pending. |
| F11: reset/refresh synchronization | Pending. |
| F12: external calls retain database transactions | Pending; worker cross-store coordination must preserve deletion consistency. |
| F13: email delivery after commit | Pending. |
| F14: conversation activity timestamps | Pending. |
| F15: concurrent first-time Google sign-in | Pending. |

## Verification

Every implementation step runs Ruff, the full test suite, API lifespan startup and `/health`, Alembic offline metadata loading, and Celery task registration. PostgreSQL-specific concurrency claims require separate real-PostgreSQL integration coverage; SQLite tests alone are insufficient.
