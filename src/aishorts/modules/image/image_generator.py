from aishorts.modules.image.image_providers import ImageProvider, ImageResult
import inspect
import asyncio
from aishorts.modules.script.script import Reel


class ImageGenerator:
    """
    Parameters:
    """

    def __init__(
        self, provider: str = "unsplash", api_key: str | None = None, **kwargs
    ):
        self.provider = provider.lower()

        cls = ImageProvider.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown Image provider '{provider}'")

        self.image_gen = cls(api_key, **kwargs)

    async def get_images(self, queries: list[str], **kwargs) -> list[ImageResult]:

        func = self.image_gen.get_images

        if inspect.iscoroutinefunction(func):
            return await func(queries, **kwargs)
        else:
            print("Running sync IMAGES in thread...")
            return asyncio.to_thread(func, queries, **kwargs)

    async def get_reel_images(self, reel: Reel, **kwargs) -> list[ImageResult]:

        func = self.image_gen.get_reel_images

        if inspect.iscoroutinefunction(func):
            return await func(reel, **kwargs)
        else:
            print("Running sync IMAGES in thread...")
            return asyncio.to_thread(func, reel, **kwargs)
