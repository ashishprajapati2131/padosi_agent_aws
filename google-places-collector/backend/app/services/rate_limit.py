"""In-process sliding window. One replica only — see the README for the limit."""

from __future__ import annotations

import threading
import time
from collections import deque

from app.config import get_settings
from app.services.errors import RateLimitError


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def reserve_search(self, user_id: int, ip: str, cost: int = 1) -> None:
        settings = get_settings()
        self._consume(
            f"user:{user_id}",
            settings.max_searches_per_minute,
            cost,
            user_message=self._user_message(settings.max_searches_per_minute, cost),
        )
        self._consume(
            f"ip:{ip}",
            settings.max_searches_per_minute_ip,
            cost,
            user_message="Too many searches from this network. Please wait and try again.",
        )

    def reserve_details(self, user_id: int) -> None:
        settings = get_settings()
        limit = settings.max_detail_requests_per_minute
        self._consume(
            f"details:{user_id}",
            limit,
            1,
            user_message=f"You have reached the limit of {limit} place detail requests per minute. Please wait and try again.",
        )

    def _user_message(self, limit: int, cost: int) -> str:
        if cost > 1:
            return (
                f"This request needs {cost} searches, which is above the limit of {limit} per minute."
            )
        return f"You have reached the limit of {limit} searches per minute. Please wait and try again."

    def _consume(self, key: str, limit: int, cost: int, user_message: str) -> None:
        if cost > limit:
            raise RateLimitError(user_message)
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= 60:
                events.popleft()
            if len(events) + cost > limit:
                raise RateLimitError(user_message)
            stamp = time.monotonic()
            events.extend([stamp] * cost)


limiter = RateLimiter()
