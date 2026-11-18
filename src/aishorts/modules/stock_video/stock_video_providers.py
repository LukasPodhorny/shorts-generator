"""Stock footage providers. Search terms come from scripts; file URLs never do."""

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel, Field, TypeAdapter

from aishorts.modules.provider import Provider
from aishorts.modules.script.script import MediaAttribution


@dataclass
class StockClip:
    path: str
    attribution: MediaAttribution


def probe_clip(path: str) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration", "-of", "json", path,
    ], check=True, capture_output=True, text=True, timeout=20)
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    streams = data.get("streams", [])
    if not streams or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Stock file has no playable video stream")
    if not (0 < streams[0].get("width", 0) <= 7680 and 0 < streams[0].get("height", 0) <= 7680):
        raise ValueError("Stock video dimensions are outside supported bounds")
    return {**streams[0], "duration": duration}


class StockVideoProvider(Provider):
    @abstractmethod
    async def get_clip(self, keywords: str, orientation: str, output_dir: Path) -> StockClip | None:
        pass


class LibraryEntry(BaseModel):
    path: str
    keywords: list[str] = Field(min_length=1)
    creator: str = Field(min_length=1, max_length=100)
    source_url: str = Field(default="", max_length=240)
    license: str = Field(min_length=1, max_length=120)


class LibraryStockVideo(StockVideoProvider):
    """Search an operator-curated local library, without network access or keys."""

    provider_name = "library"

    def __init__(self, manifest_path=None, max_bytes=120 * 1024 * 1024, **kwargs):
        manifest_path = manifest_path or os.getenv("STOCK_VIDEO_MANIFEST")
        self.max_bytes = max_bytes
        self.entries = []
        self.root = Path(".")
        if manifest_path:
            manifest = Path(manifest_path).resolve()
            self.root = manifest.parent
            self.entries = TypeAdapter(list[LibraryEntry]).validate_json(manifest.read_text())

    async def get_clip(self, keywords, orientation, output_dir):
        tokens = set(re.findall(r"\w+", keywords.casefold()))
        ranked = sorted(self.entries, key=lambda entry: len(
            tokens & set(re.findall(r"\w+", " ".join(entry.keywords).casefold()))
        ), reverse=True)
        for entry in ranked:
            if not tokens.intersection(re.findall(r"\w+", " ".join(entry.keywords).casefold())):
                continue
            source = (self.root / entry.path).resolve()
            if not source.is_relative_to(self.root):
                raise ValueError("Stock library paths must stay inside the manifest directory")
            if source.suffix.lower() not in {".mp4", ".mov", ".webm"} or source.stat().st_size > self.max_bytes:
                raise ValueError("Unsupported or oversized stock library file")
            await asyncio.to_thread(probe_clip, str(source))
            output_dir.mkdir(parents=True, exist_ok=True)
            dest = output_dir / f"{uuid.uuid4().hex}{source.suffix.lower()}"
            await asyncio.to_thread(shutil.copyfile, source, dest)
            return StockClip(str(dest), MediaAttribution(
                provider="Local library", creator=entry.creator,
                source_url=entry.source_url, license=entry.license,
            ))
        return None


class PexelsStockVideo(StockVideoProvider):
    provider_name = "pexels"
    SEARCH_URL = "https://api.pexels.com/v1/videos/search"
    DOWNLOAD_HOSTS = {"videos.pexels.com", "player.vimeo.com", "player.vimeo.com.cdn.cloudflare.net"}

    def __init__(self, api_key=None, timeout=45, max_bytes=120 * 1024 * 1024, **kwargs):
        self.api_key = api_key or os.getenv("PEXELS_API_KEY")
        if not self.api_key:
            raise ValueError("The pexels stock provider requires PEXELS_API_KEY")
        self.timeout = timeout
        self.max_bytes = max_bytes

    @classmethod
    def _safe_download_url(cls, url):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in cls.DOWNLOAD_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError("Pexels returned an unsupported download host")
        return url

    async def _search(self, session, keywords, orientation):
        for attempt in range(3):
            async with session.get(
                self.SEARCH_URL, params={"query": keywords, "orientation": orientation, "per_page": 12},
                headers={"Authorization": self.api_key}, allow_redirects=False,
            ) as response:
                if (response.status == 429 or response.status >= 500) and attempt < 2:
                    await asyncio.sleep(1 + attempt)
                    continue
                response.raise_for_status()
                return await response.json()

    @staticmethod
    def select_file(data, orientation):
        candidates = []
        target = 16 / 9 if orientation == "landscape" else 9 / 16
        for video in data.get("videos", []):
            if not (1 <= float(video.get("duration") or 0) <= 180):
                continue
            for file in video.get("video_files", []):
                w, h = file.get("width") or 0, file.get("height") or 0
                if file.get("file_type") != "video/mp4" or not file.get("link") or min(w, h) < 480 or max(w, h) > 1920:
                    continue
                if (w >= h) != (orientation == "landscape"):
                    continue
                # Prefer a matching crop and HD, without downloading 4K masters.
                score = abs(w / h - target) * 10 + abs(max(w, h) - 1280) / 1920
                candidates.append((score, video, file))
        return min(candidates, key=lambda c: c[0])[1:] if candidates else None

    async def _download(self, session, url, path):
        # Credentials are sent only to the fixed API endpoint, never the CDN.
        for _ in range(4):
            self._safe_download_url(url)
            async with session.get(url, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    url = response.headers.get("Location", "")
                    continue
                response.raise_for_status()
                if response.content_length and response.content_length > self.max_bytes:
                    raise ValueError("Stock video exceeds the download size limit")
                size = 0
                with path.open("wb") as stream:
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ValueError("Stock video exceeds the download size limit")
                        stream.write(chunk)
                return
        raise ValueError("Too many stock video download redirects")

    async def get_clip(self, keywords, orientation, output_dir):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            data = await self._search(session, keywords, orientation)
            chosen = self.select_file(data, orientation)
            if chosen is None:
                return None
            video, file = chosen
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{uuid.uuid4().hex}.mp4"
            try:
                await self._download(session, file["link"], path)
                await asyncio.to_thread(probe_clip, str(path))
                return StockClip(str(path), MediaAttribution(
                    provider="Pexels", creator=(video.get("user") or {}).get("name") or "Pexels contributor",
                    source_url=video.get("url") or "https://www.pexels.com",
                    license="Pexels License: https://www.pexels.com/license/",
                ))
            except BaseException:
                path.unlink(missing_ok=True)
                raise


class AutoStockVideo(StockVideoProvider):
    provider_name = "auto"

    def __init__(self, **kwargs):
        self.provider = (PexelsStockVideo(**kwargs) if kwargs.get("api_key") or os.getenv("PEXELS_API_KEY")
                         else LibraryStockVideo(**kwargs))

    async def get_clip(self, keywords, orientation, output_dir):
        return await self.provider.get_clip(keywords, orientation, output_dir)
