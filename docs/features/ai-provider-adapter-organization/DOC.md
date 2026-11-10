# AI Provider Adapter Organization

## Goal

Keep each AI provider's integration boundary explicit while sharing only behavior that is truly common. This separates native DeepSeek from OpenRouter even though both expose an OpenAI-compatible API.

## Module Responsibilities

- `app/infrastructure/ai/factory.py` reads environment configuration and composes the configured text and embedding adapters.
- `app/infrastructure/ai/providers/deepseek.py` owns the DeepSeek text adapter and its native API endpoint.
- `app/infrastructure/ai/providers/openrouter.py` owns the OpenRouter text adapter and endpoint.
- `app/infrastructure/ai/providers/gemini.py` owns Gemini text generation and embeddings.
- `app/infrastructure/ai/providers/openai_compatible.py` contains shared Chat Completions transport and response parsing used by DeepSeek and OpenRouter.
- `app/ai/contracts.py`, `app/ai/ports.py`, and `app/ai/prompts.py` remain the shared application contracts, interfaces, and prompts. Provider modules do not define product prompts.

## Runtime Behavior

This is an organization-only refactor. Provider selection, environment variable names, model defaults, request behavior, and persisted data remain unchanged. `AI_TEXT_PROVIDER=deepseek` selects the native DeepSeek adapter; `AI_TEXT_PROVIDER=openrouter` selects OpenRouter, which can use the DeepSeek model identifier configured for OpenRouter. Gemini remains responsible for embeddings.

## Configuration

The factory continues to use `DEEPSEEK_API_KEY` and `DEEPSEEK_TEXT_MODEL` for native DeepSeek, `OPENROUTER_API_KEY` and `OPENROUTER_TEXT_MODEL` for OpenRouter, and the existing Gemini variables for Gemini text and embeddings. No provider credentials are accepted from mobile requests.
