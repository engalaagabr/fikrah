# Localized Unsupported Chat Answers

## Status

Implemented.

## Behavior

Chat answers must use the question's language and must be grounded in current notes from the selected project. If the model marks an answer as supported but none of its cited notes can be validated against the retrieved, current project notes, the Backend discards that answer. It then asks the same configured text generator for an unsupported-answer response with no note evidence, preserving the user's question and recent conversation history so the refusal can use the question's language.

The Backend releases database locks before the additional LLM call, then reacquires the conversation lock and checks that no newer message arrived. It persists the response with `supported: false` and no sources only when the generator returns an unsupported, non-empty answer. If the generator returns a supported answer despite receiving no notes, or returns no answer, the request fails with `503` rather than exposing an ungrounded answer or a fixed English fallback.

## Boundaries

- Prompt composition and grounding rules stay in `app/llm/`.
- The chat application service validates citations and owns the retry/refusal workflow.
- Provider adapters remain unaware of product prompts and chat policy.
- This fallback does not introduce a supported-language allowlist; supported languages remain a product decision.

## Verification

The changed Python module was formatted and lint-checked. Tests were not run.
