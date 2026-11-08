# Redis Worker Technology Decision

**Status: Recommendation for review.** Redis is the approved job broker. The Python worker library and delivery guarantees are not yet approved.

## Requirements

- FastAPI accepts note-processing requests without holding the mobile request open for the full AI operation.
- Processing continues when the mobile application closes.
- Processing state and user-visible results remain in PostgreSQL, the source of truth.
- Failures are recorded and can be retried without losing the note.
- Redis carries small job messages; note text and AI results should not be stored as queue payloads or Redis results.

## Candidates

| Library | Fit | Tradeoffs |
|---|---|---|
| ARQ | Asyncio-native Python job queue built around Redis. It supports coroutine workers, job timeouts, retries, and configurable attempt limits. | Smaller and simpler surface area for this async FastAPI service; less of a general-purpose task platform than Celery. |
| Celery | Mature general-purpose task queue with a stable Redis broker transport and configurable acknowledgement/re-delivery behavior. | Broader configuration and operational surface than this initial async-only workload needs. |

The comparison is based on the projects' official documentation: [ARQ documentation](https://arq-docs.helpmanual.io/), [ARQ releases](https://github.com/python-arq/arq/releases), and [Celery Redis broker documentation](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

## Recommendation

Use **ARQ** as the Redis-backed worker library for the initial Backend. Its asyncio-native worker model matches FastAPI and the async SQLAlchemy/Qdrant clients already selected. Keep the authoritative job state in PostgreSQL; ARQ's Redis job results are not the API's source of truth.

## Delivery and Recovery Requirements

- Configure Redis persistence for queued work. Redis documents RDB snapshots and AOF; AOF with `appendfsync everysec` limits the expected loss window to about one second, while RDB-only snapshots may lose work since the last snapshot. See [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
- Treat queue delivery as at-least-once. Processing handlers must be idempotent because retries or worker recovery can execute a job more than once.
- Keep note processing state and retry outcome in PostgreSQL.
- Preserve a durable enqueue intent in PostgreSQL and reconcile pending processing records with Redis after dispatch failures or Redis recovery. Redis is the broker, not the only record that work exists.
- Do not put note text, PDFs, audio files, or AI responses in Redis job payloads. Queue only the note identifier and minimal job metadata.

These delivery requirements do not yet define the concrete PostgreSQL outbox schema, retry limits/backoff, worker count, or Redis deployment settings. Confirm those with the implementation plan before coding the worker.
