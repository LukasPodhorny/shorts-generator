from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
import asyncio
import aiohttp
from dataclasses import dataclass
import os
from aishorts.utils.r2_handler import CloudflareR2
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

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("UNSPLASH_API_KEY")
        self.base_url = "https://api.unsplash.com/search/photos"

    async def _fetch_query(
        self, session: aiohttp.ClientSession, query: str, id: int
    ) -> ImageResult:
        """Fetch one image for a single query"""
        params = {"query": query, "per_page": 1, "client_id": self.api_key}

        try:
            async with session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    if results:
                        img = results[0]

                        raw_url = img["urls"]["raw"]

                        print(raw_url)
                        path = CloudflareR2.download_presigned_file(
                            url=raw_url, path=self.OUTPUT_DIR, ext=".jpg"
                        )
                        return ImageResult(
                            media=MediaFile(
                                id=id,  # Convert string ID to int
                                url=raw_url,  # or 'full', 'raw', 'small'
                                path=path,
                            ),
                            alt=img.get("alt_description") or img.get("description"),
                        )
                    return ImageResult(
                        media=MediaFile(
                            id=id,  # Convert string ID to int
                            url=None,  # or 'full', 'raw', 'small'
                            path="output/image/transparent.png",
                        ),
                        alt="transparent",
                    )
                else:
                    return None
        except Exception as e:
            print(f"Error fetching query '{query}': {e}")
            return None

    async def get_images(self, queries: list[str]) -> list[ImageResult]:
        """Fetch images for all queries concurrently"""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_query(session, query, id=id)
                for id, query in enumerate(queries)
            ]
            results = await asyncio.gather(*tasks)
            return results

    async def get_reel_images(self, reel: Reel) -> list[ImageResult]:
        """Fetch images for all queries concurrently"""

        queries = []

        for block in reel.blocks:
            if block.media:
                if block.media.type == "image":
                    queries.append(block.media.keywords)

        return await self.get_images(queries=queries)
