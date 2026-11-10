# Redis Worker Technology Decision

**Status: Celery selected.** Redis is the approved job broker. Local Redis persistence and configurable retry/recovery limits are implemented. Production worker capacity remains deployment-specific.

## Requirements

- FastAPI accepts note-processing requests without holding the mobile request open for the full LLM operation.
- Processing continues when the mobile application closes.
- Processing state and user-visible results remain in PostgreSQL, the source of truth.
- Failures are recorded and can be retried without losing the note.
- Redis carries small job messages; note text and LLM results should not be stored as queue payloads or Redis results.

## Candidates

| Library | Fit | Tradeoffs |
|---|---|---|
| ARQ | Asyncio-native Python job queue built around Redis. It supports coroutine workers, job timeouts, retries, and configurable attempt limits. | Smaller and simpler surface area for this async FastAPI service; less of a general-purpose task platform than Celery. |
| Celery | Mature general-purpose task queue with a stable Redis broker transport and configurable acknowledgement/re-delivery behavior. | Broader configuration and operational surface than this initial async-only workload needs. |

The comparison is based on the projects' official documentation: [ARQ documentation](https://arq-docs.helpmanual.io/), [ARQ releases](https://github.com/python-arq/arq/releases), and [Celery Redis broker documentation](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

## Selection

Use **Celery** with Redis as the broker for note processing. PostgreSQL remains authoritative for note state and processing outcomes; Celery result storage will not be used as the API source of truth.

## Delivery and Recovery Requirements

- Configure Redis persistence for queued work. The local development stack uses AOF with `appendfsync everysec`; production Redis persistence is deployment-specific. Redis documents RDB snapshots and AOF; AOF with `appendfsync everysec` limits the expected loss window to about one second, while RDB-only snapshots may lose work since the last snapshot. See [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
- Treat queue delivery as at-least-once. Processing handlers must be idempotent because retries or worker recovery can execute a job more than once.
- Keep note processing state and retry outcome in PostgreSQL.
- Preserve a durable enqueue intent in PostgreSQL and reconcile pending processing records with Redis after dispatch failures or Redis recovery. Redis is the broker, not the only record that work exists.
- Do not put note text, PDFs, audio files, or LLM responses in Redis job payloads. Queue only the note identifier and minimal job metadata.

The note API persists processing intent in PostgreSQL before queue dispatch. Keep queue payloads limited to note/job identifiers, and make handlers idempotent because late acknowledgement and redelivery can run a task more than once. Retry/backoff, stale-job recovery, dispatch cadence/batch size, and broker visibility timeout are environment-configurable; see [`docs/features/celery-recovery-config/overview.md`](../celery-recovery-config/overview.md). Production worker count and Redis deployment settings remain deployment-specific.
