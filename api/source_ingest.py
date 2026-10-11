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
import re
from urllib.parse import urlparse

from aishorts.modules.ingest import ContentIngestor

logger = logging.getLogger("ShortsGenerator.SourceIngest")

# Pull http(s) URLs out of freeform prose. Deliberately permissive on the URL
# body; trailing sentence punctuation is trimmed off afterwards so "watch
# https://youtu.be/x?si=y." does not capture the period.
_URL_RE = re.compile(r"""https?://[^\s<>"'`)\]}]+""", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>\"'`"


def extract_links(text: str | None) -> list[str]:
    """Return the http(s) URLs found in free text, de-duplicated, in order."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
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
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return not (host == "localhost" or host.endswith((".local", ".internal")))


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
) -> str:
    """Convert files + links to one labeled Markdown blob (best effort).

    Mirrors `ContentIngestor.build_context`, but tolerant: a single source that
    fails to fetch/convert is logged and skipped rather than failing the whole
    request, so one dead link can't sink an otherwise-valid generation.
    """
    files = files or []
    links = links or []
    if not files and not links:
        return ""

    ingestor = ContentIngestor()
    parts: list[str] = []

    async def _file(ref: str) -> None:
        try:
            md = await ingestor.file_to_markdown(ref)
        except Exception:
            logger.warning("Failed to ingest file %s; skipping", ref, exc_info=True)
            return
        label = ref.split("/")[-1] or ref
        if not md:
            logger.warning("File %s produced empty Markdown", ref)
        parts.append(f"--- Document: {label} ---\n{md}\n")

    async def _link(url: str) -> None:
        try:
            md = await ingestor.link_to_markdown(url)
        except Exception:
            logger.warning("Failed to ingest link %s; skipping", url, exc_info=True)
            return
        if not md:
            logger.warning("Link %s produced empty Markdown", url)
        parts.append(f"--- Link: {url} ---\n{md}\n")

    # Files first (stable order), then links, ingested concurrently within group.
    await asyncio.gather(*[_file(f) for f in files])
    await asyncio.gather(*[_link(u) for u in links])

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
