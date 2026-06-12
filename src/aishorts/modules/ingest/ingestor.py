"""
Unified input ingestion built on MarkItDown.

Every input source -- local files, R2 object keys, file URLs, and web links
(plain websites, YouTube videos, Wikipedia articles, RSS feeds, ...) -- is
converted to Markdown so any LLM provider can consume it as plain text.

Images are described with a vision LLM (Gemma via the Gemini API's
OpenAI-compatible endpoint) plugged into MarkItDown's `llm_client` hook, and
audio files are transcribed when the optional speech dependencies are
installed.
"""

import asyncio
import logging
import os
import re
import tempfile
import uuid
from urllib.parse import urlparse

import aiofiles
import aiohttp
from markitdown import MarkItDown, UnsupportedFormatException

DEFAULT_VISION_MODEL = "gemma-4-31b-it"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

DEFAULT_IMAGE_PROMPT = (
    "Describe this image in detail so it can be used as source material for a "
    "video script. Include any visible text, diagrams, formulas, and data."
)

# Gemma models served through the Gemini API wrap their reasoning in
# <thought>...</thought> blocks inside the message content.
_THOUGHT_RE = re.compile(r"<thought>.*?</thought>", re.DOTALL)

# Many sites (e.g. Wikipedia) reject the default python-requests User-Agent.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _get_r2_presigned_url(key: str) -> str:
    """Generate a presigned URL for an R2 object using environment variables."""
    import boto3

    endpoint_url = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    if not all([endpoint_url, access_key, secret_key, bucket]):
        raise ValueError("R2 environment variables not configured")

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,  # 1 hour
    )
    return url


async def _ensure_local_file(
    file_ref: str, session: aiohttp.ClientSession
) -> tuple[str, bool]:
    """
    Helper to ensure a file reference is a local path.
    If it's a URL, it downloads it to a temp file.
    If it's an R2 key (e.g. 'uploads/...'), it generates a presigned URL and downloads.
    Returns (file_path, is_temporary).
    """
    # Check if it's an R2 key (not a URL and not a local path)
    if not file_ref.startswith(("http://", "https://")) and not os.path.isabs(file_ref):
        # Assume it's an R2 key - generate presigned URL
        file_ref = _get_r2_presigned_url(file_ref)

    if file_ref.startswith(("http://", "https://")):
        parsed = urlparse(file_ref)
        ext = os.path.splitext(parsed.path)[1] or ".bin"
        temp_name = f"temp_llm_{uuid.uuid4()}{ext}"
        temp_path = os.path.join(tempfile.gettempdir(), temp_name)

        async with session.get(file_ref) as resp:
            resp.raise_for_status()
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)
        return temp_path, True
    return file_ref, False


class _SanitizedCompletions:
    def __init__(self, inner_client):
        self._inner = inner_client

    def create(self, **kwargs):
        response = self._inner.chat.completions.create(**kwargs)
        for choice in response.choices:
            content = getattr(choice.message, "content", None)
            if content:
                choice.message.content = _THOUGHT_RE.sub("", content).strip()
        return response


class _SanitizedChat:
    def __init__(self, inner_client):
        self.completions = _SanitizedCompletions(inner_client)


class _VisionClient:
    """OpenAI-compatible facade that strips Gemma <thought> blocks from replies.

    MarkItDown only calls `client.chat.completions.create(...)`, so this thin
    duck-typed wrapper is all that is needed.
    """

    def __init__(self, inner_client):
        self.chat = _SanitizedChat(inner_client)


class ContentIngestor:
    """Converts heterogeneous input sources to Markdown.

    files: local paths, R2 object keys, or http(s) URLs pointing at documents.
           Downloaded if remote, then converted from the local copy.
    links: web URLs converted in place by MarkItDown so its URL-aware
           converters (YouTube, Wikipedia, RSS, Bing SERP, generic HTML)
           can kick in.
    """

    def __init__(
        self,
        vision_model: str | None = None,
        gemini_api_key: str | None = None,
        image_prompt: str | None = None,
    ):
        self.vision_model = vision_model or os.getenv(
            "MARKITDOWN_VISION_MODEL", DEFAULT_VISION_MODEL
        )
        self._gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.image_prompt = image_prompt or DEFAULT_IMAGE_PROMPT
        self._markitdown: MarkItDown | None = None
        self.logger = logging.getLogger("ShortsGenerator.ContentIngestor")

    def _get_markitdown(self) -> MarkItDown:
        if self._markitdown is None:
            llm_client = None
            if self._gemini_api_key:
                from openai import OpenAI

                llm_client = _VisionClient(
                    OpenAI(
                        api_key=self._gemini_api_key,
                        base_url=GEMINI_OPENAI_BASE_URL,
                    )
                )
            else:
                self.logger.warning(
                    "GEMINI_API_KEY not set; images will only yield metadata, "
                    "not LLM descriptions."
                )
            import requests

            session = requests.Session()
            session.headers.update({"User-Agent": _USER_AGENT})

            self._markitdown = MarkItDown(
                enable_plugins=False,
                llm_client=llm_client,
                llm_model=self.vision_model,
                llm_prompt=self.image_prompt,
                requests_session=session,
            )
        return self._markitdown

    def _convert(self, source: str) -> str:
        """Blocking conversion of a local path or URL to Markdown."""
        try:
            result = self._get_markitdown().convert(source)
        except UnsupportedFormatException as e:
            raise ValueError(f"Unsupported input type: {source}") from e
        return (result.markdown or "").strip()

    async def file_to_markdown(self, file_ref: str) -> str:
        """Convert a single file reference (local path, R2 key, or URL)."""
        async with aiohttp.ClientSession() as session:
            filepath, is_temp = await _ensure_local_file(file_ref, session)
        try:
            return await asyncio.to_thread(self._convert, filepath)
        finally:
            if is_temp:
                try:
                    os.remove(filepath)
                except OSError:
                    pass

    async def link_to_markdown(self, url: str) -> str:
        """Convert a web link (website, YouTube video, Wikipedia, RSS, ...)."""
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Links must be http(s) URLs, got: {url}")
        return await asyncio.to_thread(self._convert, url)

    async def build_context(
        self,
        files: list[str] | None = None,
        links: list[str] | None = None,
    ) -> str:
        """Convert all sources and join them into one labeled Markdown block."""
        parts: list[str] = []

        for file_ref in files or []:
            label = os.path.basename(urlparse(file_ref).path) or file_ref
            markdown = await self.file_to_markdown(file_ref)
            parts.append(f"--- Document: {label} ---\n{markdown}\n")

        for url in links or []:
            markdown = await self.link_to_markdown(url)
            parts.append(f"--- Link: {url} ---\n{markdown}\n")

        return "\n\n".join(parts)
