# Recorded Audio Transcription

## Confirmed behavior

The mobile application can send a recording to the backend and receive text.
The user selected Gemini `gemini-3.5-transcribe`, **SMART** transcription, and a
text-only response. SMART removes disfluencies and applies spoken corrections
and formatting; it is not a verbatim transcript or a note-refinement proposal.
Language is detected by Gemini without requesting translation.

This adds an optional backend audio path to the earlier mobile-only extraction
boundary. The note endpoints still accept text only. No note is created, no
project is selected, and no processing job is queued by transcription. The mobile
application can review/edit the returned text and save it through the existing
note-creation endpoint with its own idempotency key. PDF handling is unchanged.

## Mobile API contract

| Item | Contract |
| --- | --- |
| Endpoint | `POST /v1/transcriptions` |
| Purpose | Convert recorded speech to text before the user saves a note. |
| When called | After recording, when the mobile user requests transcription. |
| Authentication | Existing bearer access token; active session required. |
| Request | `multipart/form-data` with exactly one binary field named `file`; no extra fields. Set the file's audio MIME type. |
| Response | `200` and `{"text": "transcribed speech"}`; no note ID or stored transcription ID. |
| Budget | Existing per-user LLM budget (default 10 requests/minute); Redis outage fails closed. |
| File size | Default/hard maximum 10 MiB; may be reduced with `FIKRAH_TRANSCRIPTION_MAX_BYTES`. |

Supported upload media types are `audio/wav`, `audio/mp3`, `audio/mpeg`,
`audio/m4a`, `audio/aac`, `audio/ogg`, `audio/flac`, and `audio/webm`.
`audio/x-wav`, `audio/x-m4a`, and `audio/mp4` are normalized to the corresponding
supported provider type. MIME parameters such as `codecs=opus` are accepted.
The provider validates the actual audio encoding; filenames are not used as paths.

```bash
curl http://localhost:8000/v1/transcriptions \
  -H "Authorization: Bearer $FIKRAH_API_ACCESS_TOKEN" \
  -F 'file=@voice.wav;type=audio/wav'
```

The interactive `scripts/test_api_endpoints.py` also discovers this endpoint's
multipart schema and prompts for a file path and MIME type.

| Status | Meaning |
| --- | --- |
| `401` | Missing, invalid, expired, or revoked authentication. |
| `413` | File or total multipart body is too large. |
| `415` | Wrong request content type or unsupported file media type. |
| `422` | Missing/duplicate file, extra form fields, malformed upload, rejected audio, or an empty speech result. |
| `429` | LLM request budget exhausted; `Retry-After` is returned. |
| `503` | Missing provider configuration, provider/network failure, timeout, incomplete/malformed response, or unavailable request-budget store. |

This is synchronous, non-streaming processing with a 90-second provider deadline
and no automatic provider retries. No idempotency key is required because there
is no local persisted result; retrying may make another billable provider call.
It is intended for short recordings. Gemini's standard maximum is one hour, and
the provider can truncate longer audio while reporting completion. This backend
does not decode files to measure duration: clients must keep recordings below that
limit. A timeout never returns a partial transcript as a successful result.

## Layers and resource ownership

1. `app/api/body_limits.py` bounds buffering before parsing. Only POST requests to
   this registered path get the audio allowance, including 64 KiB for multipart
   overhead. All other endpoints retain `FIKRAH_REQUEST_MAX_BYTES` unchanged.
2. `app/api/v1/transcriptions.py` authenticates and enforces the existing budget
   before opening the multipart form. It permits one file and zero text fields,
   closes temporary uploads, releases the authentication read transaction before
   external work, and maps service errors to HTTP responses.
3. `app/services/transcription_service.py` validates size/media type/content and
   owns the asynchronous provider client using `aclosing`, including cancellation.
4. `LLMProviderFactory.create_audio_transcriber()` constructs a Gemini-specific
   implementation of `app/llm/ports.py::AudioTranscriber`. Text-provider selection
   does not change the transcription provider or model.
5. `app/llm/providers/gemini_transcription.py` implements only transport and
   response parsing. It calls the Interactions REST API with inline base64 audio,
   `store=false`, and the selected SMART configuration. It accepts only completed
   responses and bounds the provider response to 1 MiB.

FIKRAH does not retain uploaded audio or transcripts in PostgreSQL, Qdrant, or an
object store. Multipart handling can use a temporary spooled file; it is closed
before calling Gemini. Inline input avoids the separate Gemini Files API upload.
`store=false` disables interaction persistence; it does not override Google's
general data-handling terms. Audio and provider response bodies are not logged.

## Configuration and compatibility

- Existing `GEMINI_API_KEY`: used without adding another credential.
- New `GEMINI_TRANSCRIPTION_MODEL`: defaults to `gemini-3.5-transcribe`.
- New `FIKRAH_TRANSCRIPTION_MAX_BYTES`: defaults to `10485760`; valid values are
  1 through 10485760. It cannot raise the hard ceiling.
- Existing environment names, defaults, text generation and embedding behavior
  remain unchanged. No schema migration is needed.
- Direct `httpx` transport uses API revision `2026-05-20`, avoiding a major Google
  SDK upgrade for the new transcription configuration. Existing SDK consumers
  continue using their current interfaces.

## Verification

Automated coverage includes payload construction, SMART selection, non-persistence,
provider status/JSON/size/timeout handling, client closure and cancellation,
validation before client creation, HTTP authentication, request budgets, multipart
constraints, transaction release, OpenAPI schema, and interactive file uploads.
Body-limit tests verify declared/chunked oversize rejection and that unrelated
routes retain their smaller allowance. Live verification uses synthetic speech,
never a personal recording.

On 2026-11-21, all **228 tests** passed (54 new transcription/tooling checks), as
did Ruff, API startup, Alembic metadata/offline SQL and Celery registration.
Fresh Python 3.12 Docker images built successfully. The running endpoint returned
`401` without authentication and `200` with a verified test account. SMART turned
the synthetic spoken correction from Tuesday to Wednesday into:
`The meeting is on Wednesday at 2:00 p.m.` The live API also returned the expected
`415`, `422`, and `413` for wrong MIME type, an empty recording, and a file over
10 MiB. The endpoint tester uploaded the same recording successfully. Database
checks confirmed that transcription created no note or processing job; the test
account and its credentials were removed afterward.

## Official references

- [Gemini transcription guide](https://aistudio.google.com/docs/transcribe)
- [Gemini 3.5 Transcribe model](https://aistudio.google.com/docs/models/gemini-3.5-transcribe)
- [Interactions API](https://aistudio.google.com/api-reference/interactions-api)
- [Inline file input](https://aistudio.google.com/docs/file-input-methods#inline-data)
