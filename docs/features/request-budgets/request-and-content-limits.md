# Request and Content Limits

## Approved defaults

- Five password-login attempts per normalized email per 60-second window.
- Ten requests that initiate LLM work per authenticated user per 60-second window: note create/update/retry, refinement regeneration/acceptance, search and chat messages.
- 100,000 characters per note or refinement proposal, including generated proposals.
- 416,384 bytes per HTTP body, allowing UTF-8 content and JSON overhead. Both declared sizes and chunked bodies are checked before JSON parsing/authentication.

Configure `FIKRAH_LOGIN_LIMIT_PER_MINUTE`, `FIKRAH_LLM_LIMIT_PER_MINUTE`, `FIKRAH_NOTE_MAX_CHARACTERS`, and `FIKRAH_REQUEST_MAX_BYTES`; all must be positive. Existing environment names/defaults are preserved. `.env` is not modified.

Counters use Redis atomic Lua increment/expiry operations. Their keys hash identity scopes rather than storing raw email addresses. Windows expire 60 seconds after their first request; they are fixed windows, not a rolling log. All API processes share the same counters. Exceeding a budget returns `429` with `Retry-After`; an unavailable budget store returns `503` rather than silently disabling protection. Read-only note polling does not consume the LLM budget. An oversized body returns `413`; an over-limit note returns `422`.

Password hashing/verification also uses a nonblocking four-operation process budget. A saturated process returns `429` instead of creating an unbounded Argon2 workload; cancellation does not free capacity until the underlying operation ends.

Repeated processing retries for a queued/processing note return its existing state without changing generation or adding jobs. A saved content edit still queues a new generation as required; an older external call may finish, but attempt/revision fencing prevents it from writing a stale result.

## Verification

API tests cover login/LLM rejection, read-only polling, bounded content and idempotent pending retries. Middleware tests cover declared and chunked oversize bodies. Set `FIKRAH_TEST_REDIS_URL` to an isolated Redis instance for a 20-way concurrency test that permits exactly five requests in one window. External store failures are tested separately.

Reference: [Redis atomic counter/rate-limiter patterns](https://redis.io/docs/latest/commands/incr/).
