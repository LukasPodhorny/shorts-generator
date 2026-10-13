"""Tests for the TLS-aware Redis client factory (api/redis_client.py)."""

import pytest

from api.redis_client import redis_client


def test_rediss_disables_cert_verification():
    # Heroku Key-Value Store serves rediss:// outside the default CA trust.
    client = redis_client("rediss://user:pass@host:6380/0")
    assert client.connection_pool.connection_kwargs["ssl_cert_reqs"] == "none"
    assert client.connection_pool.connection_class.__name__ == "SSLConnection"


def test_plain_redis_untouched():
    client = redis_client("redis://localhost:6379/0")
    assert "ssl_cert_reqs" not in client.connection_pool.connection_kwargs


def test_default_url_from_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert redis_client().connection_pool is not None


def test_missing_url_raises(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValueError, match="REDIS_URL"):
        redis_client()
