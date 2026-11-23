"""Per-IP rate limiting for the MCP OAuth endpoints (brute-force protection).

Redis shares counters across dynos. Without Redis, a bounded in-memory store
protects the single-web-dyno deployment; its counters reset on restart.
"""

import logging
import os
import threading
import time

from fastapi.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

logger = logging.getLogger("pdftoreel.ratelimit")

# Paths as seen by the mounted sub-app (the /mcp prefix is stripped).
THROTTLED_PATHS = ("/authorize", "/token", "/register")
WINDOW_SECONDS = 60


def limit_per_minute() -> int:
    try:
        return max(1, int(os.getenv("MCP_AUTH_RATE_LIMIT_PER_MINUTE", "60")))
    except ValueError:
        return 60


class RedisCounter:
    """Fixed-window counter store on Redis (INCR + EXPIRE)."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def hit(self, key: str) -> int:
        count = self._redis.incr(key)
        if count == 1:
            self._redis.expire(key, WINDOW_SECONDS)
        return int(count)


class MemoryCounter:
    """Fixed-window counter for a single web process, capped at 10,000 IPs."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int:
        window = int(time.monotonic() // WINDOW_SECONDS)
        with self._lock:
            previous_window, count = self._counts.get(key, (-1, 0))
            if previous_window != window:
                count = 0
            if key not in self._counts and len(self._counts) >= 10_000:
                self._counts.pop(next(iter(self._counts)))
            count += 1
            self._counts[key] = (window, count)
            return count


def build_store():
    """Return a shared Redis counter or a local counter for one web dyno."""
    url = os.getenv("REDIS_URL")
    if not url:
        return MemoryCounter()
    from api.redis_client import redis_client

    return RedisCounter(redis_client(url))


def _client_ip(scope) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-for")
    if forwarded:
        return forwarded.decode().split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Throttle OAuth handshake endpoints per client IP."""

    def __init__(self, app, store=None) -> None:
        self.app = app
        self.store = store if store is not None else build_store()

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] != "http"
            or self.store is None
            or scope.get("path", "").rstrip("/") not in THROTTLED_PATHS
        ):
            await self.app(scope, receive, send)
            return
        key = f"mcp:rl:{scope['path']}:{_client_ip(scope)}"
        try:
            count = await run_in_threadpool(self.store.hit, key)
        except Exception:
            logger.warning("Rate limiter store error; failing open", exc_info=True)
            await self.app(scope, receive, send)
            return
        if count > limit_per_minute():
            response = JSONResponse(
                {"detail": "Too many requests; slow down and retry."},
                status_code=429,
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
