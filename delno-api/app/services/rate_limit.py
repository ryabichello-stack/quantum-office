"""In-memory rate limiting for public widget endpoints (Commit 2)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_sec: float | None = None


class InMemoryRateLimiter:
    """Process-local sliding window limiter — sufficient for single-node MVP."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_sec: int) -> RateLimitResult:
        now = time.monotonic()
        window_start = now - window_sec
        with self._lock:
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= limit:
                retry = window_sec - (now - hits[0])
                return RateLimitResult(allowed=False, retry_after_sec=max(0.1, retry))
            hits.append(now)
            self._hits[key] = hits
        return RateLimitResult(allowed=True)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_widget_limiter = InMemoryRateLimiter()


def get_widget_rate_limiter() -> InMemoryRateLimiter:
    return _widget_limiter


def check_widget_rate_limit(
    *,
    site_key: str,
    client_ip: str,
    action: str,
) -> RateLimitResult:
    settings = get_settings()
    if action == "message":
        limit = settings.widget_rate_limit_messages_per_minute
    else:
        limit = settings.widget_rate_limit_per_minute
    window = settings.widget_rate_limit_window_sec
    key = f"{action}:{site_key}:{client_ip}"
    return _widget_limiter.check(key, limit=limit, window_sec=window)
