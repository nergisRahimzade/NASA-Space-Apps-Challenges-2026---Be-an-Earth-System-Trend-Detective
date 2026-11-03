"""A small in-memory rate limiter.

ESD-D07-BE. Each visitor (keyed by IP address) may make `limit` requests in
any rolling window of `window_s` seconds. It lives in the API's memory, so
it resets when the server restarts. That is enough for a demo API; a large
site would use a shared store such as Redis instead.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(self, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> bool:
        """Record one request for key and say whether it is allowed. limit <= 0 means no limit."""
        if limit <= 0:
            return True
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()  # forget requests older than the window
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        """Forget every recorded request (used by tests)."""
        with self._lock:
            self._hits.clear()
