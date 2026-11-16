# API Endpoint Testing Tools

## Purpose

Provide two ways to exercise the running FIKRAH API: call one endpoint at a
time from an interactive menu, or run an automated authenticated workflow using
temporary data.

## Requirements

- Start the API and required services with Docker Compose.
- Use a local or dedicated test environment, not production.
- Install dependencies with `pip install -r requirements.txt`.
- Use a verified email/password test account for the automated workflow.
- Configure a working LLM provider and worker for optional LLM checks.

Configure automated workflow credentials without committing them:

```bash
export FIKRAH_SMOKE_EMAIL='verified-test-account@example.com'
export FIKRAH_SMOKE_PASSWORD='your-test-password-at-least-15-chars'
```

## Test Endpoints One at a Time

Start the interactive endpoint browser:

```bash
python scripts/test_api_endpoints.py
```

The script loads the running API's OpenAPI schema and lists each method, path,
and summary. Select an endpoint, enter any path values, query string, required
headers, JSON body, and expected HTTP status. It prints the received status
and response, then returns to the endpoint list. Enter `q` to quit.

Supply an access token through the environment for authenticated routes:

```bash
export FIKRAH_API_ACCESS_TOKEN='your-test-access-token'
python scripts/test_api_endpoints.py
```

Or select `POST /v1/auth/login`; the script keeps returned access and refresh
tokens in memory for later requests. Use `@access_token` or `@refresh_token` as
a JSON string value in a later request body, such as
`{"refresh_token":"@refresh_token"}`. Tokens are redacted from displayed
responses and never saved to disk.

Set `FIKRAH_API_BASE_URL` or pass `--base-url` to use a different API address.
Pass `--timeout` to change the request timeout.

## Run an Automated Workflow

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

The interactive endpoint browser lists every operation exposed by the running
OpenAPI schema, including authentication, projects, notes, refinement,
connections, search, graph retrieval, and chat. It sends only the endpoint you
select and compares the actual status with the expected status you enter.

The automated default workflow covers API health, authentication enforcement,
email/password login, current-user retrieval, refresh and logout, the protected
General project, project create/read/rename/delete, note
create/list/read/update/delete, and conversation list/create/read/delete.

`--with-llm` additionally waits for note processing and checks connections,
knowledge graph retrieval, semantic search, and sending a chat message. These
calls can incur provider usage and require the worker and LLM configuration to
be available.

Google sign-in and email-link confirmation need provider-issued ID tokens or
one-time links. The interactive browser can call these routes when you enter
the required values. The automated workflow does not request password-reset
emails or change account credentials.

## Safety

The automated workflow never registers or deletes an account and does not
modify existing projects or notes. It creates a uniquely named project and
test data inside it, then deletes the conversation, note, and project. It signs
out and revokes its refresh token at the end. Do not interrupt it before
cleanup completes.

The interactive browser sends the request and body you enter to the selected
API. Mutating endpoints can create, update, or delete data, so use a local or
dedicated test environment and disposable test data.
