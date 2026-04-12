from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
import asyncio
import aiohttp
from dataclasses import dataclass
import os
from aishorts.utils.r2_handler import download_from_url
from aishorts.modules.script.script import Reel, AssetType
from typing import Any


@dataclass
class ImageResult:
    media: MediaFile
    alt: str | None = None


class ImageProvider(Provider):
    OUTPUT_DIR = os.getenv("IMAGE_OUTPUT_DIR") or "output/image"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def populate_reel(self, reel: Reel, **kwargs) -> None:
        pass


class Unsplash(ImageProvider):
    provider_name = "unsplash"

    def __init__(self, max_concurrent_downloads: int = 5, api_key: str | None = None):
        self.api_key = api_key or os.getenv("UNSPLASH_API_KEY")
        self.base_url = "https://api.unsplash.com/search/photos"
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)

    async def _search_query(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_width: int,
        max_height: int,
    ) -> list[tuple[str, str | None]]:
        """Search for an image URL without downloading it."""
        params = {"query": query, "per_page": 10, "client_id": self.api_key}

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
                        return []

                    candidates = []
                    for img in results:
                        raw_url = img["urls"]["raw"]
                        # Request PNG format from Unsplash (Imgix)
                        raw_url += (
                            "&" if "?" in raw_url else "?"
                        ) + f"fm=png&w={max_width}&h={max_height}&fit=max"
                        candidates.append(
                            (
                                raw_url,
                                img.get("alt_description") or img.get("description"),
                            )
                        )

                    return candidates
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(
                    f"Attempt {attempt + 1}/3 failed for query '{query}'. Retrying... Error: {e}"
                )
                if attempt == 2:
                    print(f"Error fetching query '{query}' after 3 attempts.")
                    return []
                await asyncio.sleep(2**attempt)  # 1, 2 seconds backoff

            except Exception as e:
                # Catch any other unexpected errors and don't retry
                print(f"An unexpected error occurred fetching query '{query}': {e}")
                return []
        return []

    async def get_images(
        self,
        queries: list[str],
        max_width: int,
        max_height: int,
        ids: list[Any] | None = None,
    ) -> list[ImageResult | None]:
        """Fetch images for all queries concurrently"""
        if ids is None:
            ids = list(range(len(queries)))

        # Phase 1: Search for all images in parallel (low bandwidth, high latency)
        # We use a shorter timeout for searches
        search_timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=search_timeout) as session:
            search_tasks = [
                self._search_query(session, query, max_width, max_height)
                for query in queries
            ]
            search_results_lists = await asyncio.gather(*search_tasks)

        # Deduplicate images
        seen_urls = set()
        search_results = []

        for candidates in search_results_lists:
            selected = None
            for url, alt in candidates:
                if url not in seen_urls:
                    selected = (url, alt)
                    seen_urls.add(url)
                    break
            search_results.append(selected)

        # Phase 2: Download images (high bandwidth)
        # We use the semaphore here to prevent network saturation
        total = len(queries)
        completed = 0

        async def _bounded_download(url, alt, id):
            nonlocal completed
            async with self.semaphore:
                path = await download_from_url(url, self.OUTPUT_DIR, ".png")
                completed += 1
                print(f"Downloading images: {completed}/{total}")
                return ImageResult(media=MediaFile(id=id, url=url, path=path), alt=alt)

        download_tasks = []
        for url_data, id in zip(search_results, ids):
            if url_data:
                url, alt = url_data
                download_tasks.append(_bounded_download(url, alt, id))
            else:
                # Preserve order with None for failed searches
                download_tasks.append(asyncio.sleep(0, result=None))

        results = await asyncio.gather(*download_tasks)
        return results

    async def populate_reel(
        self,
        reel: Reel,
        max_width: int,
        max_height: int,
    ) -> None:
        """Fetch images for all queries concurrently"""

        queries = []
        ids = []

        for i, block in enumerate(reel.blocks):
            if AssetType.IMAGES in block.valid_assets and block.media:
                for media_item in block.media:
                    if media_item.type == "image":
                        queries.append(media_item.keywords)
                        ids.append((i, media_item.id))

        results = await self.get_images(
            queries=queries, max_width=max_width, max_height=max_height, ids=ids
        )

        for res in results:
            if res:
                block_idx, media_id = res.media.id
                block = reel.blocks[block_idx]
                block.assets.media_map[media_id] = res.media.path
                block.assets.media_url_map[media_id] = res.media.url


class RunPodAI(ImageProvider):
    """AI image generation provider using RunPod's public z-image-turbo endpoint."""

    provider_name = "runpod_ai"

    def __init__(
        self,
        max_concurrent_downloads: int = 3,
        api_key: str | None = None,
        endpoint_id: str = "z-image-turbo",
        default_size: str = "1024*1024",
        default_strength: float = 0.8,
        enable_safety_checker: bool = True,
        timeout: int = 300,
    ):
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.endpoint_id = endpoint_id
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
        self.default_size = default_size
        self.default_strength = default_strength
        self.enable_safety_checker = enable_safety_checker
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)

    async def _generate_image(
        self,
        prompt: str,
        size: str | None = None,
        strength: float | None = None,
        seed: int = -1,
    ) -> tuple[str, str]:
        """Generate an image and return (image_url, prompt).

        The /run endpoint is async — it returns a job ID. We poll /status/{id}
        until the job completes, then extract the output URL.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "input": {
                "prompt": prompt,
                "size": size or self.default_size,
                "strength": strength if strength is not None else self.default_strength,
                "seed": seed,
                "output_format": "png",
                "enable_safety_checker": self.enable_safety_checker,
            }
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Submit the job
            async with session.post(
                self.base_url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

            # If the response already contains output, return it directly
            image_url = data.get("output")
            if image_url:
                return image_url, prompt

            # Otherwise, poll for completion
            job_id = data.get("id")
            if not job_id:
                raise RuntimeError(f"No job ID or output in RunPod response: {data}")

            status_url = f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{job_id}"
            poll_interval = 1.0

            while True:
                await asyncio.sleep(poll_interval)
                async with session.get(status_url, headers=headers) as status_resp:
                    status_resp.raise_for_status()
                    status_data = await status_resp.json()

                status = status_data.get("status")
                if status == "COMPLETED":
                    image_url = status_data.get("output")
                    if not image_url:
                        raise RuntimeError(
                            f"RunPod job completed but no output: {status_data}"
                        )
                    return image_url, prompt
                elif status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                    raise RuntimeError(
                        f"RunPod job {status}: {status_data.get('error', status_data)}"
                    )
                # IN_QUEUE / IN_PROGRESS — keep polling
                poll_interval = min(poll_interval * 1.5, 5.0)

    async def _download_image(self, url: str, prompt: str, id: Any) -> ImageResult:
        """Download generated image to local storage."""
        async with self.semaphore:
            path = await download_from_url(url, self.OUTPUT_DIR, ".png")
            return ImageResult(
                media=MediaFile(id=id, url=url, path=path), alt=prompt
            )

    async def get_image(
        self,
        prompt: str,
        size: str | None = None,
        strength: float | None = None,
        seed: int = -1,
        id: Any = 0,
    ) -> ImageResult:
        """Generate and download a single image."""
        image_url, alt = await self._generate_image(
            prompt=prompt, size=size, strength=strength, seed=seed
        )
        return await self._download_image(image_url, alt, id)

    async def get_images(
        self,
        prompts: list[str],
        sizes: list[str] | None = None,
        strengths: list[float] | None = None,
        seeds: list[int] | None = None,
        ids: list[Any] | None = None,
        **kwargs,  # Accept but ignore max_width/max_height from base class
    ) -> list[ImageResult | None]:
        """Generate and download multiple images concurrently."""
        if ids is None:
            ids = list(range(len(prompts)))

        if sizes is None:
            sizes = [None] * len(prompts)
        if strengths is None:
            strengths = [None] * len(prompts)
        if seeds is None:
            seeds = [-1] * len(prompts)

        total = len(prompts)
        completed = 0

        async def _generate_and_download(prompt, size, strength, seed, id):
            nonlocal completed
            try:
                image_url, alt = await self._generate_image(
                    prompt=prompt, size=size, strength=strength, seed=seed
                )
                result = await self._download_image(image_url, alt, id)
                completed += 1
                print(f"Generated images: {completed}/{total}")
                return result
            except Exception as e:
                print(f"Failed to generate image for prompt '{prompt}': {e}")
                completed += 1
                return None

        tasks = [
            _generate_and_download(prompt, size, strength, seed, id)
            for prompt, size, strength, seed, id in zip(
                prompts, sizes, strengths, seeds, ids
            )
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    async def populate_reel(
        self,
        reel: Reel,
        **kwargs,  # Accept but ignore max_width/max_height
    ) -> None:
        """Generate images for all media items in the reel."""
        prompts = []
        ids = []

        for i, block in enumerate(reel.blocks):
            if AssetType.IMAGES in block.valid_assets and block.media:
                for media_item in block.media:
                    if media_item.type == "image":
                        prompts.append(media_item.keywords)
                        ids.append((i, media_item.id))

        results = await self.get_images(prompts=prompts, ids=ids, **kwargs)

        for res in results:
            if res:
                block_idx, media_id = res.media.id
                block = reel.blocks[block_idx]
                block.assets.media_map[media_id] = res.media.path
                block.assets.media_url_map[media_id] = res.media.url
