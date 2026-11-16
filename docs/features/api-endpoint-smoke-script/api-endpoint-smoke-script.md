# API Endpoint Smoke Script

## Purpose

Provide a repeatable command-line check for the running FIKRAH API. The script
uses an existing verified email/password account and creates a temporary
project, note, and conversation. It deletes those resources and revokes its
refresh token when finished.

## Requirements

- Start the API and its required local services with Docker Compose.
- Use a verified test account. Do not use a production account.
- Install the project dependencies with `pip install -r requirements.txt`.
- For the optional LLM checks, configure a working LLM provider and worker.

Configure credentials without committing them:

```bash
export FIKRAH_SMOKE_EMAIL='verified-test-account@example.com'
export FIKRAH_SMOKE_PASSWORD='your-test-password-at-least-15-chars'
```

## Run

Run the account, project, note CRUD, and conversation lifecycle checks:

```bash
python scripts/smoke_api.py
```

Include asynchronous note processing, knowledge connections, graph retrieval,
semantic search, and a chat message:

```bash
python scripts/smoke_api.py --with-llm
```

Override the API address or processing timeout when needed:

```bash
python scripts/smoke_api.py --base-url http://localhost:8000 --timeout 120 --with-llm
```

## Coverage

The default run checks API health, authentication enforcement, email/password
login, current-user retrieval, refresh and logout, the protected General
project, project create/read/rename/delete, note create/list/read/update/delete,
and conversation list/create/read/delete.

`--with-llm` additionally waits for note processing and checks connections,
knowledge graph retrieval, semantic search, and sending a chat message. These
calls can incur provider usage and require the worker and LLM configuration to
be available.

Google sign-in and email-link confirmation are not automated because they need
provider-issued Google ID tokens or one-time links delivered to a test inbox.
Password-reset email requests are also excluded to avoid changing the test
account's credentials or triggering email rate limits.

## Safety

The script never registers or deletes an account and does not modify existing
projects or notes. It creates a uniquely named project and all test data inside
that project, then deletes the conversation, note, and project. It signs out
and revokes the refresh token at the end. Do not interrupt the script before
cleanup completes.
