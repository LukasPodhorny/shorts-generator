"""Redis client factory (Heroku TLS aware).

Heroku Key-Value Store serves `rediss://` with a certificate outside the
default CA trust, so plain `Redis.from_url` fails with
`CERTIFICATE_VERIFY_FAILED`. Verification is disabled for `rediss://` URLs
only (same-trust-boundary managed service; traffic stays encrypted);
`redis://` URLs are untouched.
"""

import os

from redis import Redis


def redis_client(url: str | None = None) -> Redis:
    """Return a Redis client for `url` (default: `REDIS_URL`)."""
    target = url or os.getenv("REDIS_URL")
    if not target:
        raise ValueError("REDIS_URL is not set")
    kwargs = {"ssl_cert_reqs": "none"} if target.startswith("rediss://") else {}
    return Redis.from_url(target, **kwargs)
