# AI Provider Factory and Note Worker

## Approved Providers

DeepSeek, Gemini, and OpenRouter have separate adapter modules under `app/infrastructure/ai/providers/`. `AIProviderFactory` in `app/infrastructure/ai/factory.py` is the composition root: it reads deployment configuration and creates the selected adapter. The local environment selects OpenRouter with `deepseek/deepseek-v4.1-flash`; deployments may select `deepseek`, `gemini`, or `openrouter` through `AI_TEXT_PROVIDER`. Provider and model are selected by deployment configuration, not by mobile requests.

The provider package keeps provider-specific endpoints in `deepseek.py`, `openrouter.py`, and `gemini.py`. DeepSeek uses its native API endpoint; OpenRouter uses its own endpoint and model namespace. Their common Chat Completions request/response handling lives in `openai_compatible.py`. Shared prompts and application contracts remain in `app/ai/`, outside the infrastructure adapters.

Gemini is the embedding provider for every deployment. DeepSeek's current API documentation exposes text/chat model APIs but no embeddings API; Gemini provides text embeddings. Using one embedding model keeps all note vectors in a compatible embedding space when the text-generation provider changes. The default Gemini embedding model is `gemini-embedding-001` with 768 dimensions, which is one of Google's recommended output sizes.

Text model defaults are `deepseek-flash`, `gemini-3.8-flash`, and `deepseek/deepseek-v4.1-flash` through OpenRouter. Deployments can override them with `DEEPSEEK_TEXT_MODEL`, `GEMINI_TEXT_MODEL`, and `OPENROUTER_TEXT_MODEL`. The embedding model and dimension can be set with `GEMINI_EMBEDDING_MODEL` and `GEMINI_EMBEDDING_DIMENSIONS`.

## Note Analysis Contract

The selected text model returns a validated structure:

- `title`: generated in the same language as the original note; stored only if the user did not supply a title.
- `refinement_proposal`: a clearer rewrite in the original language, preserving the author's meaning. It remains a proposal and never replaces saved content automatically.
- `concepts`: up to eight concise concepts.

DeepSeek and OpenRouter use OpenAI-compatible Chat Completions endpoints with JSON output; DeepSeek uses `https://api.deepseek.com`, while OpenRouter uses `https://openrouter.ai/api/v1`. Gemini uses the official Google GenAI Python SDK and Pydantic-backed structured output. Provider credentials are loaded only by the worker process. The mobile API never accepts provider keys or provider selection.

## Celery and Durable Dispatch

- The API commits a `note_processing_jobs` row in PostgreSQL with the note revision before worker processing.
- Celery uses Redis as the broker and does not use Redis for task results. The task payload contains only the job ID.
- Celery Beat periodically publishes undispatched or stale processing jobs and Qdrant cleanup requests. PostgreSQL remains the recovery source if Redis is unavailable.
- Workers use late acknowledgements. Tasks are idempotent by database job ID and note revision; duplicate delivery does not replace a newer revision.
- Qdrant stores one vector point per note ID with user/project/revision metadata. Raw note text stays in PostgreSQL, not in Qdrant payloads.
- A failed AI or Qdrant request retries up to three times by default with exponential delay and jitter, then marks the current note revision `failed` while retaining its content. Retry count and delay are configurable; stale dispatch/processing recovery is documented in [`docs/features/celery-recovery-config/overview.md`](../celery-recovery-config/overview.md).

## Configuration

Required environment variables:

- `DATABASE_URL`: PostgreSQL URL used by API and workers.
- `REDIS_URL`: Redis broker URL.
- `QDRANT_URL`: Qdrant server URL.
- `GEMINI_API_KEY`: required for embeddings; also used for text generation when Gemini is selected.
- `DEEPSEEK_API_KEY`: required when DeepSeek is selected for text generation.
- `OPENROUTER_API_KEY`: required when OpenRouter is selected for text generation.
- `AI_TEXT_PROVIDER`: `deepseek`, `gemini`, or `openrouter`.

Optional model/dimension variables are listed above; `QDRANT_API_KEY` and `QDRANT_NOTES_COLLECTION` configure secured Qdrant deployments.

Run the combined Celery worker and single Beat scheduler with:

```bash
celery -A app.worker.celery_app:celery_app worker --beat --loglevel=INFO
```

Only one Beat scheduler should run for this initial deployment command.

## References

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) and [DeepSeek model list](https://api-docs.deepseek.com/api/list-models/)
- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) and [OpenRouter model catalog](https://openrouter.ai/models/deepseek/deepseek-v4.1-flash)
- [Google GenAI SDK](https://ai.google.dev/gemini-api/docs/libraries), [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), and [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings)
- [Celery Redis broker](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html) and [Celery task acknowledgement](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
