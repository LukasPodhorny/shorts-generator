from aishorts.modules.latex.latex_providers import (
    LatexProvider,
    LatexResult,
    Resolution,
)
from aishorts.modules.script.script import Reel
from aishorts.utils.async_utils import await_or_thread
from aishorts.utils.image_utils import ImageStyle, style_image
import asyncio


class LatexGenerator:
    """
    Parameters:
    """

    def __init__(
        self,
        provider: str = "real_latex",
        image_style: ImageStyle | None = None,
        **kwargs,
    ):
        self.image_style = image_style or ImageStyle()

        self.provider = provider.lower()

        cls = LatexProvider.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown LaTex provider '{provider}'")

        self.latex_gen = cls(**kwargs)

    async def get_images(
        self,
        latex_codes: list[str],
        resolution: Resolution = Resolution(400, 200),
        **kwargs,
    ) -> list[LatexResult]:

        func = self.latex_gen.get_images
        results = await await_or_thread(func, latex_codes, resolution, **kwargs)

        async def _style_task(result):
            await asyncio.to_thread(
                style_image, result.media.path, result.media.path, self.image_style
            )

        await asyncio.gather(*[_style_task(r) for r in results])

        return results

    async def get_reel_images(
        self, reel: Reel, resolution: Resolution = Resolution(400, 200), **kwargs
    ) -> list[LatexResult]:

        func = self.latex_gen.get_reel_images
        results = await await_or_thread(func, reel, resolution, **kwargs)

        async def _style_task(result):
            await asyncio.to_thread(
                style_image, result.media.path, result.media.path, self.image_style
            )

        await asyncio.gather(*[_style_task(r) for r in results])

        return results
