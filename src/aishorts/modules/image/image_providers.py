from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
import asyncio
import aiohttp
from dataclasses import dataclass
import os
from aishorts.utils.r2_handler import download_from_url, CloudflareR2
from aishorts.modules.script.script import Reel


@dataclass
class ImageResult:
    media: MediaFile
    alt: str | None = None


class ImageProvider(Provider):
    OUTPUT_DIR = os.getenv("IMAGE_OUTPUT_DIR") or "output/image"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def get_reel_images(self, reel: Reel, **kwargs) -> list[ImageResult]:
        pass


class Unsplash(ImageProvider):
    provider_name = "unsplash"

    def __init__(self, max_concurrent_downloads: int = 5, api_key: str | None = None):
        self.api_key = api_key or os.getenv("UNSPLASH_API_KEY")
        self.base_url = "https://api.unsplash.com/search/photos"
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)

    async def _fetch_query(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_width: int,
        max_height: int,
        id: int,
    ) -> ImageResult | None:
        """Fetch one image for a single query, with retries."""
        params = {"query": query, "per_page": 1, "client_id": self.api_key}

        for attempt in range(3):
            try:
                # 1. Search for the image
                async with session.get(self.base_url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    results = data.get("results", [])

                    if not results:
                        # No results found, don't retry.
                        print(f"No Unsplash results for query: '{query}'")
                        return None

                    img = results[0]
                    raw_url = img["urls"]["raw"]
                    # Request PNG format from Unsplash (Imgix)
                    raw_url += (
                        "&" if "?" in raw_url else "?"
                    ) + f"fm=png&w={max_width}&h={max_height}&fit=max"

                    # 2. Download the image
                    path = CloudflareR2.get_random_filepath(self.OUTPUT_DIR, ".png")
                    async with session.get(raw_url) as img_resp:
                        img_resp.raise_for_status()
                        with open(path, "wb") as f:
                            async for chunk in img_resp.content.iter_chunked(8192):
                                f.write(chunk)

                    return ImageResult(
                        media=MediaFile(
                            id=id,  # Convert string ID to int
                            url=raw_url,  # or 'full', 'raw', 'small'
                            path=path,
                        ),
                        alt=img.get("alt_description") or img.get("description"),
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(
                    f"Attempt {attempt + 1}/3 failed for query '{query}'. Retrying... Error: {e}"
                )
                if attempt == 2:
                    print(f"Error fetching query '{query}' after 3 attempts.")
                    return None
                await asyncio.sleep(2**attempt)  # 1, 2 seconds backoff

            except Exception as e:
                # Catch any other unexpected errors and don't retry
                print(f"An unexpected error occurred fetching query '{query}': {e}")
                return None
        return None

    async def get_images(
        self,
        queries: list[str],
        max_width: int,
        max_height: int,
        ids: list[int] | None = None,
    ) -> list[ImageResult | None]:
        """Fetch images for all queries concurrently"""
        if ids is None:
            ids = list(range(len(queries)))

        timeout = aiohttp.ClientTimeout(
            total=180
        )  # 180-second total timeout per operation

        total = len(queries)
        completed = 0

        async def _bounded_fetch(session, query, max_width, max_height, id):
            nonlocal completed
            async with self.semaphore:
                result = await self._fetch_query(
                    session, query, max_width, max_height, id
                )
                completed += 1
                print(f"Downloading images: {completed}/{total}")
                return result

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                _bounded_fetch(session, query, max_width, max_height, id=id)
                for query, id in zip(queries, ids)
            ]
            results = await asyncio.gather(*tasks)
            return results

    async def get_reel_images(
        self,
        reel: Reel,
        max_width: int,
        max_height: int,
    ) -> list[ImageResult | None]:
        """Fetch images for all queries concurrently"""

        queries = []
        ids = []

        for i, block in enumerate(reel.blocks):
            if block.media:
                if block.media.type == "image":
                    queries.append(block.media.keywords)
                    ids.append(i)

        return await self.get_images(
            queries=queries, max_width=max_width, max_height=max_height, ids=ids
        )
