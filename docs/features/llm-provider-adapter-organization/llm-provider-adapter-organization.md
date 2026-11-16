# LLM Provider Adapter Organization

## Goal

Keep each LLM provider's integration boundary explicit while sharing only behavior that is truly common. This separates native DeepSeek from OpenRouter even though both expose an OpenAI-compatible API.

## Module Responsibilities

- `app/infrastructure/llm/factory.py` reads environment configuration and composes the configured text and embedding adapters.
- `app/infrastructure/llm/providers/deepseek.py` owns `DeepSeekTextGenerator` and its native API endpoint.
- `app/infrastructure/llm/providers/openrouter.py` owns `OpenRouterTextGenerator` and its endpoint.
- `app/infrastructure/llm/providers/gemini.py` owns `GeminiTextGenerator` and Gemini embeddings.
- `app/infrastructure/llm/providers/openai_compatible.py` contains shared Chat Completions transport and response parsing used by DeepSeek and OpenRouter.
- `app/llm/contracts.py` and `app/llm/ports.py` define shared result contracts and the `StructuredTextGenerator` port. `app/llm/prompts.py` and `app/llm/use_cases.py` own product prompt composition, note/chat workflows, and output contracts. Provider adapters handle provider transport and structured response validation only.

## Runtime Behavior

Provider selection and model defaults remain unchanged. The application-facing package is `app.llm`, the infrastructure package is `app.infrastructure.llm`, and `LLMProviderFactory` is the composition root. `LLM_TEXT_PROVIDER=deepseek` selects the native DeepSeek adapter; `LLM_TEXT_PROVIDER=openrouter` selects OpenRouter, which can use the DeepSeek model identifier configured for OpenRouter. Gemini remains responsible for embeddings. Deployment configuration uses `LLM_TEXT_PROVIDER`.

## Configuration

The factory continues to use `DEEPSEEK_API_KEY` and `DEEPSEEK_TEXT_MODEL` for native DeepSeek, `OPENROUTER_API_KEY` and `OPENROUTER_TEXT_MODEL` for OpenRouter, and the existing Gemini variables for Gemini text and embeddings. No provider credentials are accepted from mobile requests.
