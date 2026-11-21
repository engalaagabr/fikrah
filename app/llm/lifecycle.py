"""Own a provider for one synchronous operation, including resource cleanup."""

from collections.abc import Callable
from contextlib import closing
from typing import TypeVar

from app.llm.ports import CloseableProvider

Provider = TypeVar("Provider", bound=CloseableProvider)
Result = TypeVar("Result")


def run_with_provider(
    factory: Callable[[], Provider], operation: Callable[[Provider], Result]
) -> Result:
    """Create, use, and close on the executing thread, even if the operation fails.

    Async callers must offload this entire function, so cancellation of their
    coroutine cannot close a client while its synchronous request is still running.
    """
    with closing(factory()) as provider:
        return operation(provider)
