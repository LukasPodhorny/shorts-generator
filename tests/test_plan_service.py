"""Tests for source extraction and ingestion in the plan flow."""

import asyncio
import os

import pytest
from fastapi import HTTPException

# Snapshot/restore env around the api import (load_dotenv side effect).
_ENV_BEFORE_API_IMPORT = dict(os.environ)

from api.source_ingest import (  # noqa: E402
    SourceIngestError,
    extract_links,
    ingest_sources,
    is_public_http_url,
)

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
        if behavior == "empty":
            return "  "
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


def test_extract_links_accepts_bare_urls_and_parenthesized_paths():
    assert extract_links(
        "Use youtube.com/watch?v=abc and "
        "https://en.wikipedia.org/wiki/Function_(mathematics). "
        "Also [this](https://example.org/page)."
    ) == [
        "https://youtube.com/watch?v=abc",
        "https://en.wikipedia.org/wiki/Function_(mathematics)",
        "https://example.org/page",
    ]


def test_extract_links_ignores_file_names_and_email_addresses():
    assert extract_links("My notes.md and report.pdf are from me@example.com") == []


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost./private",
        "https://sub.localhost/private",
        "https://user:password@example.com/private",
        "https://[::1/private",
    ],
)
def test_public_url_check_rejects_local_aliases_and_credentials(url):
    assert not is_public_http_url(url)


def test_studio_link_guard_rejects_the_same_unsafe_targets():
    from api.routers.generate import _validate_links

    for url in [
        "https://localhost./private",
        "https://user@example.com/private",
        "https://[::1/private",
    ]:
        with pytest.raises(HTTPException) as exc:
            _validate_links([url])
        assert exc.value.status_code == 400


@pytest.mark.parametrize("behavior", ["fail", "empty", ("sleep", 30)])
def test_ingest_rejects_when_no_source_content_was_read(monkeypatch, behavior):
    _patch(monkeypatch, {"https://x.example/a": behavior})
    with pytest.raises(SourceIngestError):
        asyncio.run(ingest_sources([], ["https://x.example/a"], timeout=0.01))
