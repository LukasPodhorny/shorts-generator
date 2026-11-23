"""API-level source ingestion for the chatbot (/api/plan) entry point.

Why this lives at the API level (and not, as before, inside the core library):
the old flow handed file keys and links to `aishorts` and let the library fetch
and transcribe them at generation time. The intent parser, meanwhile, was told
NOT to read links out of the user's prose -- so a link typed directly into the
chat message was silently dropped and never ingested. This module closes that
gap by doing the ingestion here, before the core library is ever called:

  1. Links are pulled out of the freeform instruction with a regex (no LLM call,
     so a model can neither miss nor invent them).
  2. Those links, plus any files/links the user attached through the UI, are run
     through the SAME `ContentIngestor` (MarkItDown + vision/YouTube models) the
     library uses, producing one Markdown blob.
  3. The blob is folded into `input_text`. The core library is then called with
     `files=None, links=None`: it just sees text, which is all it ever did with
     ingested sources anyway.

The core library keeps its files/links options untouched -- the Studio path
(/api/generate) still relies on them. This module is plan-path only.
"""

import asyncio
import ipaddress
import logging
import os
import re
from urllib.parse import urlparse

from aishorts.modules.ingest import ContentIngestor

logger = logging.getLogger("ShortsGenerator.SourceIngest")

# Overall budget for one ingest_sources() call. This runs inside a web request
# (REST /api/plan and MCP plan_reels), and Heroku's router drops web requests
# past 30 s -- so ingestion must be bounded. Slow sources are skipped when
# another source succeeds; a request with no readable sources fails.
SOURCE_INGEST_TIMEOUT_SECONDS = float(os.getenv("SOURCE_INGEST_TIMEOUT_SECONDS", "20"))

# Pull full URLs and bare domains out of prose. The bare-domain branch accepts
# links pasted into the prompt the same way the Add Link dialog does.
_URL_RE = re.compile(
    r"""(?<![\w@./-])(?:https?://[^\s<>"'`]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#][^\s<>"'`]+)?)""",
    re.IGNORECASE,
)
_TRAILING_PUNCT = ".,;:!?]}>\"'`"
_FILE_SUFFIXES = {
    "csv", "doc", "docx", "html", "jpg", "jpeg", "json", "m4a", "md",
    "mp3", "pdf", "png", "ppt", "pptx", "rtf", "txt", "wav", "xls",
    "xlsx", "xml",
}
MAX_SOURCE_LINKS = 10


class SourceIngestError(Exception):
    """No usable content was read from the supplied sources."""


def extract_links(text: str | None) -> list[str]:
    """Return full and bare web URLs from free text, de-duplicated, in order."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        if not url.lower().startswith(("http://", "https://")):
            # Avoid treating ordinary attached-file names in prose as domains.
            host = urlparse("https://" + url).hostname or ""
            if host.rsplit(".", 1)[-1].lower() in _FILE_SUFFIXES:
                continue
            url = "https://" + url
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def is_public_http_url(url: str) -> bool:
    """True if the URL is an http(s) link to a public host (SSRF guard).

    Links are fetched server-side by the ingest layer, so internal targets
    (localhost, RFC1918, *.internal) must be rejected. This does not resolve
    DNS; it is a basic guard matching the one on /api/generate.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    host = host.rstrip(".")
    if not host or host == "localhost" or host.endswith(
        (".localhost", ".local", ".internal")
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def merge_links(*groups: list[str]) -> list[str]:
    """Concatenate link lists, dropping duplicates while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for url in group:
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


async def ingest_sources(
    files: list[str] | None,
    links: list[str] | None,
    timeout: float | None = None,
) -> str:
    """Convert files + links to one labeled Markdown blob (best effort).

    A failed source is skipped if another source succeeds. If none yields
    content, raise so generation cannot charge credits for a source-based
    request with no source material. The whole step is bounded by `timeout`
    seconds (default `SOURCE_INGEST_TIMEOUT_SECONDS`).
    """
    files = files or []
    links = links or []
    if not files and not links:
        return ""
    if timeout is None:
        timeout = SOURCE_INGEST_TIMEOUT_SECONDS

    ingestor = ContentIngestor()

    async def _file(ref: str) -> str | None:
        try:
            md = await ingestor.file_to_markdown(ref)
        except Exception:
            logger.warning("Failed to ingest file %s; skipping", ref, exc_info=True)
            return None
        label = ref.split("/")[-1] or ref
        if not md or not md.strip():
            logger.warning("File %s produced empty Markdown", ref)
            return None
        return f"--- Document: {label} ---\n{md}\n"

    async def _link(url: str) -> str | None:
        try:
            md = await ingestor.link_to_markdown(url)
        except Exception:
            logger.warning("Failed to ingest link %s; skipping", url, exc_info=True)
            return None
        if not md or not md.strip():
            logger.warning("Link %s produced empty Markdown", url)
            return None
        return f"--- Link: {url} ---\n{md}\n"

    # Files first (stable order), then links, all ingested concurrently.
    tasks = [asyncio.ensure_future(_file(f)) for f in files] + [
        asyncio.ensure_future(_link(u)) for u in links
    ]
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        logger.warning(
            "Source ingest timed out after %ss; skipping %d unfinished source(s)",
            timeout,
            len(pending),
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    parts = []
    for task in tasks:
        if task in done and not task.cancelled():
            chunk = task.result()
            if chunk:
                parts.append(chunk)
    if not parts:
        raise SourceIngestError(
            "Could not read any content from the supplied files or links. "
            "Check the sources and try again."
        )
    return "\n\n".join(parts)


def build_plan_input_text(instruction: str | None, source_markdown: str) -> str | None:
    """Fold the ingested Markdown into the text handed to the core library.

    The library is called with files/links blank, so this is the only place the
    source content reaches it. The framing mirrors the library's own so the
    script generator still distinguishes instruction from source material.
    """
    chunks: list[str] = []
    instruction = (instruction or "").strip()
    if instruction:
        chunks.append(instruction)
    if source_markdown:
        chunks.append(
            "The following is Markdown converted from the provided source(s). "
            "Use it as the source material.\n\n" + source_markdown
        )
    text = "\n\n".join(chunks)
    return text or None
