# Project Ownership Integrity

## Scope

Every note and conversation references a project owned by the same user. PostgreSQL enforces this invariant on inserts and updates, alongside the existing ownership checks in application services. The HTTP routes, request/response schemas, and transaction ownership remain unchanged.

| Table | Constraint | Reference |
| --- | --- | --- |
| `projects` | `uq_projects_id_user_id` | Unique `(id, user_id)` target for composite references. |
| `notes` | `fk_notes_project_owner` | `(project_id, user_id)` references `projects(id, user_id)`. |
| `chat_conversations` | `fk_chat_conversations_project_owner` | `(project_id, user_id)` references `projects(id, user_id)`. |

The composite foreign keys retain `ON DELETE CASCADE`. They replace the old project-ID-only foreign keys; direct user foreign keys and existing indexes are preserved. Referenced projects cannot change owners while dependent notes or conversations would become inconsistent. Valid references to another project of the same user remain possible at the database layer; this adds no mobile API for moving records.

## Migration and deployment

New revision `20261121_03_enforce_project_ownership.py` follows `20261121_02`. Existing version files and `.env` are unchanged.

The migration first counts notes and conversations with inconsistent/missing project ownership. Any mismatch aborts the upgrade with counts, without logging content, deleting records, or choosing new owners. An operator must audit the records and resolve ownership explicitly before retrying. The same guard is present in generated offline SQL.

After that guard, PostgreSQL validates every existing row when adding the new constraints. The old foreign keys are removed only after their replacements are created. DDL is transactional; validation failure rolls back the upgrade. Downgrade restores the original project-ID-only foreign keys before removing the ownership constraints and unique target.

Adding the unique constraint and validated foreign keys acquires database locks and scans existing records. Schedule deployment according to table size and traffic; this is not an online index/constraint rollout. This revision is tested on isolated PostgreSQL 16. The configured development database was unreachable during preparation, so its data was not certified or migrated.

The actual migration tests also exposed double escaping of percent-encoded URLs in `migrations/env.py`. The environment loader now passes the URL directly into the engine configuration dictionary, with a real PostgreSQL regression covering encoded connection options. No environment variable names or defaults change.

## Authorization boundary

These constraints protect consistency of project ownership. They do not implement row-level read authorization or constrain the project scope of graph links/citations. Services and repositories still derive user identity from authentication and scope every operation. Privileged SQL maintenance must follow the same ownership rules. Application deletion workflows remain responsible for durable Qdrant cleanup intents.

## Verification

- Run insert/update rejection, valid references, project-owner mutation, and user/project deletion tests against both metadata-created tables and the full Alembic history.
- Verify a populated upgrade/downgrade/upgrade round trip preserves records and constraint definitions.
- Verify invalid legacy records abort migration without being reassigned/deleted or advancing the Alembic revision.
- Verify offline SQL includes the preflight and both composite foreign keys.
- Existing API, worker, PostgreSQL concurrency, and Redis tests remain in the full regression gate.

## References

- [PostgreSQL 16 foreign key constraints](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-FK)
- [PostgreSQL 16 ALTER TABLE](https://www.postgresql.org/docs/16/sql-altertable.html)
- [SQLAlchemy composite foreign keys](https://docs.sqlalchemy.org/en/20/core/constraints.html#defining-foreign-keys)
