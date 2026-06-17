from aishorts.modules.image.image_providers import ImageProvider, ImageResult
from aishorts.modules.script.script import Reel
from aishorts.utils.async_utils import await_or_thread
from aishorts.utils.image_utils import ImageStyle, style_image, crop_to_9_16
import asyncio
from aishorts.modules.provider import MediaFile
from aishorts.modules.script.script import AssetType


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
                self.max_width,
                self.max_height,
            )

        await asyncio.gather(*[_style_task(r) for r in results])

        return results

    async def generate_thumbnail(
        self,
        prompt: str,
        output_path: str,
        width: int = 540,
        height: int = 960,
    ) -> str:
        """
        Generate a thumbnail image with 9:16 aspect ratio (vertical).

        Args:
            prompt: The prompt/keywords for image generation
            output_path: Where to save the thumbnail
            width: Target width (default 540 for vertical)
            height: Target height (default 960 for vertical)

        Returns:
            Path to the generated thumbnail
        """
        import shutil
        from PIL import Image

        got_image = False

        # Try the primary provider. Treat exceptions as "no result" so the
        # fallback still runs (e.g. RunPod returning an unparseable output shape).
        try:
            if hasattr(self.image_gen, "get_image"):
                # Use get_image with specific size for AI providers
                result = await self.image_gen.get_image(
                    prompt=prompt, size=f"{width}*{height}", id="thumbnail"
                )
                if result and result.media and result.media.path:
                    shutil.move(result.media.path, output_path)
                    got_image = True
            else:
                # For providers like Unsplash, generate and crop
                results = await self.image_gen.get_images(
                    queries=[prompt],
                    max_width=width,
                    max_height=height,
                    ids=["thumbnail"],
                )
                if results and results[0]:
                    shutil.move(results[0].media.path, output_path)
                    got_image = True
        except Exception as e:
            print(f"Thumbnail: primary provider raised {type(e).__name__}: {e}")

        # Fallback to RunPodAI if primary provider returned nothing or errored
        if not got_image:
            print(
                f"Thumbnail: primary provider returned no result, falling back to RunPodAI"
            )
            from aishorts.modules.image.image_providers import RunPodAI

            fallback = RunPodAI()
            result = await fallback.get_image(
                prompt=prompt, size=f"{width}*{height}", id="thumbnail"
            )
            shutil.move(result.media.path, output_path)

        # Ensure 9:16 aspect ratio by cropping if needed
        await asyncio.to_thread(crop_to_9_16, output_path, output_path)

        # Resize to target dimensions and compress as JPEG
        def _compress(path, w, h):
            with Image.open(path) as img:
                img = img.convert("RGB")
                img = img.resize((w, h), Image.LANCZOS)
                img.save(path, "JPEG", quality=80, optimize=True)

        await asyncio.to_thread(_compress, output_path, width, height)

        return output_path

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        """Generates images and populates the reel.blocks[i].assets fields in-place.
        Falls back to RunPodAI for any images the primary provider couldn't find."""
        func = self.image_gen.populate_reel

        # Provider now populates the reel directly
        await await_or_thread(func, reel, self.max_width, self.max_height, **kwargs)

        # Check for missing images and fall back to RunPodAI
        missing_prompts = []
        missing_ids = []
        for i, block in enumerate(reel.blocks):
            if AssetType.IMAGES in block.valid_assets:
                for media_item in block.media:
                    if (
                        media_item.type == "image"
                        and media_item.id not in block.assets.media_map
                    ):
                        missing_prompts.append(media_item.keywords)
                        missing_ids.append((i, media_item.id))

        if missing_prompts:
            from aishorts.modules.image.image_providers import RunPodAI

            print(
                f"Primary image provider returned no results for "
                f"{len(missing_prompts)} image(s), falling back to RunPodAI"
            )
            fallback = RunPodAI()
            # Calculate size string for RunPodAI based on max dimensions
            fallback_size = f"{self.max_width}*{self.max_height}"
            fallback_results = await fallback.get_images(
                prompts=missing_prompts,
                sizes=[fallback_size] * len(missing_prompts),
                ids=missing_ids,
            )
            for res in fallback_results:
                if res:
                    block_idx, media_id = res.media.id
                    block = reel.blocks[block_idx]
                    block.assets.media_map[media_id] = res.media.path
                    block.assets.media_url_map[media_id] = res.media.url

        # We need to iterate blocks to style the images that were just generated
        async def _style_task(path):
            await asyncio.to_thread(
                style_image,
                path,
                path,
                self.image_style,
                self.max_width,
                self.max_height,
            )

        # Collect results from the reel for styling
        paths_to_style = []
        for block in reel.blocks:
            if AssetType.IMAGES in block.valid_assets:
                # We only want to style images, so we iterate the media items to check type
                for media_item in block.media:
                    if (
                        media_item.type == "image"
                        and media_item.id in block.assets.media_map
                    ):
                        paths_to_style.append(block.assets.media_map[media_item.id])

        await asyncio.gather(*[_style_task(p) for p in paths_to_style])

        return reel
