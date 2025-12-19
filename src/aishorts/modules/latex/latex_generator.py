from aishorts.modules.latex.latex_providers import (
    LatexProvider,
    LatexResult,
    Resolution,
)
import inspect
import asyncio
from aishorts.modules.script.script import Reel


class LatexGenerator:
    """
    Parameters:
    """

    def __init__(self, provider: str = "local_latex", **kwargs):
        self.provider = provider.lower()

        cls = LatexProvider.get(self.provider)

        if not cls:
            raise ValueError(f"Unknown Latex provider '{provider}'")

        self.latex_gen = cls(**kwargs)

    async def get_images(
        self,
        latex_codes: list[str],
        resolution: Resolution = Resolution(400, 200),
        **kwargs,
    ) -> list[LatexResult]:

        func = self.latex_gen.get_images

        if inspect.iscoroutinefunction(func):
            return await func(latex_codes, resolution, **kwargs)
        else:
            print("Running sync LATEX in thread...")
            return await asyncio.to_thread(func, latex_codes, resolution, **kwargs)

    async def get_reel_images(
        self, reel: Reel, resolution: Resolution = Resolution(400, 200), **kwargs
    ) -> list[LatexResult]:

        func = self.latex_gen.get_reel_images

        if inspect.iscoroutinefunction(func):
            return await func(reel, resolution, **kwargs)
        else:
            print("Running sync LATEX in thread...")
            return await asyncio.to_thread(func, reel, resolution, **kwargs)
