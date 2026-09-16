"""Small bounded fixed-window limiter; Redis-backed deployment limiter is deferred behind the same interface."""
from __future__ import annotations
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

class RateLimitExceeded(RuntimeError): pass
class InMemoryRateLimiter:
    def __init__(self) -> None: self._events=defaultdict(deque); self._lock=Lock()
    def check(self, key: str, limit: int, window: float = 60) -> int:
        now=monotonic()
        with self._lock:
            events=self._events[key]
            while events and events[0] <= now-window: events.popleft()
            if len(events) >= limit: raise RateLimitExceeded()
            events.append(now); return max(1, int(window-(now-events[0])))

class RedisRateLimiter:
    def __init__(self, client) -> None: self.client=client
    def check(self, key: str, limit: int, window: float=60) -> int:
        bucket=f"rate:{key}:{int(__import__('time').time()//window)}"
        try:
            with self.client.pipeline() as pipe:
                pipe.incr(bucket); pipe.expire(bucket, int(window), nx=True); count,_=pipe.execute()
        except Exception as exc: raise RateLimitExceeded() from exc
        if count > limit: raise RateLimitExceeded()
        return int(window)
