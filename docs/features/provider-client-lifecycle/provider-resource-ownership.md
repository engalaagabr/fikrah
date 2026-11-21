# Provider Resource Ownership

## Contract

Text generators and embedding models expose `close()`. Their adapters delegate to the synchronous SDK client's close method; DeepSeek and OpenRouter inherit this from their shared transport adapter. Factories return a fresh client whose caller owns its lifetime. Model-independent prompt use cases borrow the supplied client and do not close it.

`app/llm/lifecycle.py` provides `run_with_provider(factory, operation)`: construct, use, and close one client on the executing thread, including when the operation fails. Factory failures propagate without attempting to close an instance that was never created. Cleanup failures propagate through the existing workflow error handling.

For async workflows the entire scope must run inside `asyncio.to_thread`. Cancelling an awaiting coroutine cannot stop an already running synchronous SDK call; cleanup runs after that operation exits, rather than closing its client prematurely from the event loop. This does not add task interruption, heartbeat, or deadline policy.

## Rollout

- Explicit adapter cleanup and a shared ownership helper are implemented.
- Worker analysis and embeddings each close their client before vector/database completion. If analysis fails, no embedding client is created.
- Search creates, uses, and closes its embedding model inside one background thread, before querying Qdrant or validating PostgreSQL results.
- Chat creates, uses, and closes its generator inside one background thread per generation. The client closes before citation validation, conversation conflict checks, or persistence. A localized refusal uses a fresh client from the same configured factory rather than reusing a closed client.
- Qdrant already closes its clients in `finally`; its locking/consistency policy is unchanged.

## Verification

Tests use fake SDK clients and controlled worker threads. They cover success, exceptions, factory failure, SDK close delegation, and caller cancellation, plus worker/retrieval/chat execution paths, chat conflicts and refusal generation. No live provider requests or API keys are required. API contracts, model settings, prompts, timeout/retry policy, database transactions, and Celery task names are preserved.
