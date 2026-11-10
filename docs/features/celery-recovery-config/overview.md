# Celery Recovery Configuration

## Purpose

Keep PostgreSQL as the durable source of pending work while Redis and Celery
deliver tasks. Provide explicit local Redis persistence and environment-backed
settings for retry and stale-job recovery behavior.

## Behavior

- Local Redis uses AOF with `appendfsync everysec` and the existing named volume.
- Note processing defaults to three Celery retries with a five-second
  exponential retry base and jitter.
- The dispatcher runs every 30 seconds, dispatches at most 100 rows per work
  type, and recovers queued jobs whose dispatch is older than five minutes.
- Processing jobs that remain active for 15 minutes become eligible for
  recovery. Operators can tune this to their LLM provider latency.
- The Redis visibility timeout defaults to one hour.
- All integer settings must be positive; invalid values fail worker startup.

## Configuration

| Environment variable | Default | Purpose |
| --- | ---: | --- |
| `FIKRAH_CELERY_MAX_RETRIES` | `3` | Celery retries after the initial processing attempt. |
| `FIKRAH_CELERY_RETRY_BACKOFF_SECONDS` | `5` | Base delay for exponential retry backoff. |
| `FIKRAH_CELERY_VISIBILITY_TIMEOUT_SECONDS` | `3600` | Redis broker timeout for unacknowledged tasks. |
| `FIKRAH_DISPATCH_STALE_AFTER_SECONDS` | `300` | Age at which an unpublished queued job is eligible for republishing. |
| `FIKRAH_PROCESSING_STALE_AFTER_SECONDS` | `900` | Age at which a processing job is eligible for recovery. |
| `FIKRAH_DISPATCH_INTERVAL_SECONDS` | `30` | Celery Beat reconciliation interval. |
| `FIKRAH_DISPATCH_BATCH_SIZE` | `100` | Maximum jobs or cleanup requests claimed per dispatch pass. |

The selected limits are starting defaults, not a production capacity guarantee.
Tune them against measured provider latency, job volume, and worker capacity.

## Verification

Unit coverage verifies defaults, environment overrides, and rejection of invalid
values. Worker behavior continues to be covered by the note processing tests.
