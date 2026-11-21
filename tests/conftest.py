"""Default unit/API fixtures replace external rate-budget storage only."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def isolated_request_budgets(monkeypatch):
    from app.infrastructure.container import request_budgets

    monkeypatch.setattr(request_budgets._store, "consume", AsyncMock())
