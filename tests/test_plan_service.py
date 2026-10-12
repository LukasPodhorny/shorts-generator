"""Tests for plan-service ingestion bounds (api/source_ingest.py).

ingest_sources() runs inside web requests (REST /api/plan, MCP plan_reels),
so it must be time-bounded: slow sources are skipped, never fatal.
"""

import asyncio
import os

# Snapshot/restore env around the api import (load_dotenv side effect).
_ENV_BEFORE_API_IMPORT = dict(os.environ)

from api.source_ingest import ingest_sources  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


class _FakeIngestor:
    """ContentIngestor stand-in with controllable per-source behavior."""

    def __init__(self, behaviors):
        self.behaviors = behaviors

    async def file_to_markdown(self, ref):
        return await self._run(ref)

    async def link_to_markdown(self, url):
        return await self._run(url)

    async def _run(self, key):
        behavior = self.behaviors.get(key, "ok")
        if isinstance(behavior, tuple):
            action, arg = behavior
            if action == "sleep":
                await asyncio.sleep(arg)
                return f"md-for-{key}"
            raise AssertionError(f"unknown behavior {behavior}")
        if behavior == "fail":
            raise RuntimeError("boom")
        return f"md-for-{key}"


def _patch(monkeypatch, behaviors):
    monkeypatch.setattr(
        "api.source_ingest.ContentIngestor", lambda: _FakeIngestor(behaviors)
    )


def test_ingest_keeps_order_and_labels(monkeypatch):
    _patch(monkeypatch, {})
    out = asyncio.run(ingest_sources(["k1", "k2"], ["https://x.example/a"]))
    assert out.index("--- Document: k1 ---") < out.index("--- Document: k2 ---")
    assert out.index("--- Document: k2 ---") < out.index("--- Link: https://x.example/a ---")
    assert "md-for-k1" in out


def test_ingest_skips_failures(monkeypatch):
    _patch(monkeypatch, {"bad": "fail"})
    out = asyncio.run(ingest_sources(["good", "bad"], []))
    assert "md-for-good" in out
    assert "bad" not in out


def test_ingest_timeout_keeps_completed_and_skips_pending(monkeypatch):
    _patch(monkeypatch, {"slow": ("sleep", 30)})
    out = asyncio.run(ingest_sources(["fast", "slow"], [], timeout=0.2))
    assert "md-for-fast" in out
    assert "slow" not in out
