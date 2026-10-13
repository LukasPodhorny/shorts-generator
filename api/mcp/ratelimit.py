"""Per-IP rate limiting for the MCP OAuth endpoints (brute-force protection).

Attached to the MCP sub-app via `http_app(middleware=[...])`. Redis-backed
fixed windows; without `REDIS_URL` (local dev) it is a no-op, and a Redis
outage fails open (availability over throttling) with a logged warning.
"""

import logging
import os

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


def build_store():
    """Return a counter store, or None when Redis is not configured."""
    url = os.getenv("REDIS_URL")
    if not url:
        return None
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
            logger.warning("Rate limiter Redis error; failing open", exc_info=True)
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
