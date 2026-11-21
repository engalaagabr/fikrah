"""Atomic Redis fixed-window counters shared across API processes."""

from collections.abc import Callable
from hashlib import sha256

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.services.request_budgets import RequestBudgetExceeded, RequestBudgetUnavailable

_CONSUME = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return {count, redis.call('TTL', KEYS[1])}
"""


class RedisBudgetStore:
    def __init__(self, redis_url: Callable[[], str]) -> None:
        self._redis_url = redis_url

    async def consume(self, key: str, limit: int, window_seconds: int) -> None:
        redis_key = f"fikrah:budget:{sha256(key.encode()).hexdigest()}"
        try:
            async with Redis.from_url(
                self._redis_url(), socket_connect_timeout=2, socket_timeout=2
            ) as client:
                count, ttl = await client.eval(
                    _CONSUME, 1, redis_key, limit, window_seconds
                )
        except (RedisError, OSError, ValueError) as error:
            raise RequestBudgetUnavailable from error
        if int(count) > limit:
            raise RequestBudgetExceeded(max(1, int(ttl)))
