"""Application request budgets and transport-independent failure contracts."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID


class RequestBudgetExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class RequestBudgetUnavailable(Exception):
    pass


class BudgetStore(Protocol):
    async def consume(self, key: str, limit: int, window_seconds: int) -> None: ...


class RequestBudgets:
    def __init__(
        self,
        store: BudgetStore,
        login_limit: Callable[[], int],
        llm_limit: Callable[[], int],
    ) -> None:
        self._store = store
        self._login_limit = login_limit
        self._llm_limit = llm_limit

    async def login(self, email: str) -> None:
        await self._store.consume(
            f"login:{email.strip().lower()}", self._login_limit(), 60
        )

    async def llm(self, user_id: UUID) -> None:
        await self._store.consume(f"llm:{user_id}", self._llm_limit(), 60)
