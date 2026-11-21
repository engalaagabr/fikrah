# Security and Reliability Remediation

This phase addresses the architecture/security review of commit `0975d0f`. Fixes are made in small steps with regression coverage. Existing migration versions and local `.env` are preserved.

| Finding | Status |
| --- | --- |
| F01: unverified password survives Google linking | Fixed; regression verifies the old password and pending action links cannot be used after linking. Already verified passwords remain usable. |
| F02: non-authoritative Google email linking | Fixed under the approved Gmail/Workspace authority policy; previously linked subjects remain usable. |
| F03/F04: login, request, and content budgets | Fixed under the approved defaults, with atomic Redis counters, fail-closed errors, bounded password work/body/content, and idempotent pending retries. |
| F05: worker attempt ownership | Fixed; unique attempt tokens fence completion and failure, and retries release only their own claim. |
| F06: worker lock order | Fixed; note locks precede job locks, dispatcher skips locked notes, and deletion shares project coordination with graph/vector completion. Two real PostgreSQL regressions pass. |
| F07: answers retain invalidated evidence | Fixed; losing any cited current source invalidates the entire generated answer. |
| F08: accepted public JWT placeholder | Fixed; startup and token operations reject the tracked public placeholder and missing/short secrets. |
| F09/F10: access-token invalidation and refresh replay | Fixed; JWTs are bound to revocable refresh families. Logout is per-family; replay revokes the family; reset revokes all families. |
| F11: reset/refresh synchronization | Fixed with user-first locking and a real PostgreSQL concurrent reset/refresh regression. New migration retires legacy tokens. |
| F12: external calls retain database transactions | API search/chat fixed and covered. User approved retaining worker vector-write locking temporarily to fence stale results/deletion; a slow Qdrant write can still hold project/note locks until its timeout. Moving it requires a separate vector-outbox/reconciliation design. |
| F13: email delivery after commit | Fixed; encrypted delivery intents commit atomically with account/action changes, SMTP runs without database transactions, and the worker retries failures with fenced claims. SMTP outages no longer suppress successful Google tokens. |
| F14: conversation activity timestamps | Fixed; successful message exchanges update activity even when a title already exists. |
| F15: concurrent first-time Google sign-in | Fixed; shared identity locks serialize account creation, with a real PostgreSQL concurrent sign-in regression. |

## Verification

Every implementation step runs Ruff, the full test suite, API lifespan startup and `/health`, Alembic offline metadata loading, and Celery task registration. PostgreSQL-specific concurrency claims require separate real-PostgreSQL integration coverage; SQLite tests alone are insufficient.

## Upgrade notes and remaining work

- Apply the new migrations `20261121_01` (session families) and `20261121_02` (email delivery intents) before running this code. Existing migration files and `.env` are unchanged. The session migration deliberately retires existing sessions; users must sign in again.
- Redis is required for login/LLM budgets; an unavailable limiter fails closed with `503`. See the [request limits](../../features/request-budgets/request-and-content-limits.md) for the approved defaults.
- Worker Qdrant locking remains a documented temporary consistency choice. Cross-store reconciliation, editable proposals, supported languages, and mixed-language chat remain separate open decisions.
- Broader architecture/operations debt from the review is separate from the fixed findings: neutral shared contracts, model module ownership, transport-independent error policies, database ownership constraints, graph scaling, pagination, readiness, reproducible dependencies, SDK lifetimes/deadlines, and record retention/security events.
- Account emails are at least once and require Celery Beat plus a worker for retries. JWT-key rotation requires resending any pending action links encrypted under the retired key. See [authentication](../../features/authentication/overview.md#durable-account-emails).
