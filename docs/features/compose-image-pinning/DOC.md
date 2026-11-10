# Pin the Local Qdrant Image

## Goal

Keep local development builds reproducible by using a known Qdrant release.

## Decision

Compose uses `qdrant/qdrant:v1.19.1`, matching the Qdrant image already used by
the local stack when this change was made. The floating `latest` tag could
change the database version during an otherwise unchanged rebuild.

## Upgrade Guidance

Change the image tag intentionally. Before adopting a new release, verify the
Qdrant adapter and the existing collection configuration with that release.
This pin applies only to the local development stack and does not define a
production deployment policy.
