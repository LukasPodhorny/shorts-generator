from aishorts.modules.image.image_providers import ImageProvider, ImageResult
from aishorts.modules.script.script import Reel, BlockAssets, AssetType
from aishorts.utils.async_utils import await_or_thread
from aishorts.utils.image_utils import ImageStyle, style_image
import asyncio


class ImageGenerator:
    """
    Parameters:
    """

    def __init__(
        self,
        provider: str = "unsplash",
        max_width: int = 450,
        max_height: int = 400,
        image_style: ImageStyle = None,
        max_concurrent_downloads: int = 5,
        api_key: str | None = None,
        **kwargs,
    ):
        self.provider = provider.lower()
        self.image_style = image_style or ImageStyle()
        self.max_width = max_width
        self.max_height = max_height

        cls = ImageProvider.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown Image provider '{provider}'")

        self.image_gen = cls(max_concurrent_downloads, api_key, **kwargs)

    async def get_images(self, queries: list[str], **kwargs) -> list[ImageResult]:

        func = self.image_gen.get_images

        results = await await_or_thread(
            func, queries, self.max_width, self.max_height, **kwargs
        )

        async def _style_task(result):
            if not result:
                return
            await asyncio.to_thread(
                style_image,
                result.media.path,
                result.media.path,
                self.image_style,
            )

        await asyncio.gather(*[_style_task(r) for r in results])

        return results

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates images and populates the reel.blocks[i].assets fields in-place."""
        func = self.image_gen.populate_reel

        # Provider now populates the reel directly
        await await_or_thread(func, reel, self.max_width, self.max_height, **kwargs)

        # We need to iterate blocks to style the images that were just generated
        async def _style_task(result):
            if not result:
                return
            await asyncio.to_thread(
                style_image,
                result.media.path,
                result.media.path,
                self.image_style,
            )

        # Collect results from the reel for styling
        results_to_style = []
        for block in reel.blocks:
            if AssetType.IMAGES in block.valid_assets and block.assets.image_filepath:
                # Create a temporary object or just pass path to style task
                results_to_style.append(
                    ImageResult(media=MediaFile(id=0, path=block.assets.image_filepath))
                )

        await asyncio.gather(*[_style_task(r) for r in results_to_style])

        return reel
