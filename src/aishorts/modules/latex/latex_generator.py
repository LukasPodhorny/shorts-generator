from aishorts.modules.latex.latex_providers import (
    LatexProvider,
    LatexResult,
    Resolution,
)
from aishorts.modules.script.script import Reel
from aishorts.utils.async_utils import await_or_thread
from aishorts.utils.image_utils import ImageStyle, style_image
import asyncio
from aishorts.modules.script.script import AssetType




class LatexGenerator:
    """
    Parameters:
    """

    def __init__(
        self,
        provider: str = "real_latex",
        width: int | None = None,
        height: int | None = None,
        image_style: ImageStyle | None = None,
        **kwargs,
    ):
        self.image_style = image_style or ImageStyle()
        self.width = width
        self.height = height
        self.provider = provider.lower()

        cls = LatexProvider.get(self.provider)
        self.latex_gen = cls(**kwargs)

    async def get_images(
        self,
        latex_codes: list[str],
        **kwargs,
    ) -> list[LatexResult]:

        resolution = Resolution(self.width, self.height)

        func = self.latex_gen.get_images
        results = await await_or_thread(func, latex_codes, resolution, **kwargs)

        async def _style_task(result):
            await asyncio.to_thread(
                style_image, result.media.path, result.media.path, self.image_style
            )

        await asyncio.gather(*[_style_task(r) for r in results])

        return results

    async def populate_reel(self, reel: Reel, **kwargs) -> Reel:
        resolution = Resolution(self.width, self.height)

        func = self.latex_gen.populate_reel
        await await_or_thread(func, reel, resolution, **kwargs)

        async def _style_task(path):
            await asyncio.to_thread(style_image, path, path, self.image_style)

        paths_to_style = []
        for block in reel.blocks:
            if AssetType.LATEX in block.valid_assets:
                for media_item in block.media:
                    if (
                        media_item.type == "latex"
                        and media_item.id in block.assets.media_map
                    ):
                        paths_to_style.append(block.assets.media_map[media_item.id])

        await asyncio.gather(*[_style_task(p) for p in paths_to_style])
        return reel
