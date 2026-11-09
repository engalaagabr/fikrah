# OpenRouter Text Provider

## Purpose

FIKRAH can route note analysis and project chat through OpenRouter, using the user-selected `deepseek/deepseek-v4.1-flash` model. OpenRouter is selected by backend configuration; mobile requests cannot choose a provider or model.

## Behavior

- `AIProviderFactory` creates an OpenRouter adapter using the OpenAI-compatible Chat Completions API at `https://openrouter.ai/api/v1`.
- Note analysis and chat use JSON responses validated against FIKRAH's existing Pydantic response models.
- Gemini remains the sole embedding provider, so changing text-generation providers does not change the vector embedding space.
- The provider key is read by the backend worker from environment configuration and is not stored in source control or sent to the mobile application.

## Configuration

Set these values in the deployment environment (or local `.env`):

```dotenv
AI_TEXT_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_TEXT_MODEL=deepseek/deepseek-v4.1-flash
GEMINI_API_KEY=
```

`OPENROUTER_API_KEY` is required for text analysis and chat. `GEMINI_API_KEY` remains required for note and query embeddings. The model can be changed with `OPENROUTER_TEXT_MODEL` without changing application code.

## Related Documentation

- [AI provider factory and note worker](../note-processing/ai-provider-factory.md)
- [Note management](../note-management/overview.md)
