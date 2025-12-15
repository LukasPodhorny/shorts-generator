from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import uuid
from aishorts.modules.script.script import Reel


@dataclass
class Resolution:
    width: int
    height: int


@dataclass
class LatexResult:
    media: MediaFile
    alt: str | None = None


class LatexProvider(Provider):
    OUTPUT_DIR = os.getenv("LATEX_OUTPUT_DIR") or "output/latex"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    @abstractmethod
    def get_reel_images(
        self, reel: Reel, resolution: Resolution, **kwargs
    ) -> list[LatexResult]:
        pass


class LocalLatex(LatexProvider):
    provider_name = "local_latex"

    def render_single(self, id: int, latex_code: str, resolution: Resolution):
        dpi = 100
        fig = plt.figure(
            figsize=(resolution.width / dpi, resolution.height / dpi), dpi=dpi
        )
        fig.patch.set_facecolor("white")

        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        # Start with a large font and shrink until it fits
        fontsize = min(resolution.width, resolution.height) // 5
        while fontsize > 1:
            txt = ax.text(
                0.5, 0.5, f"${latex_code}$", fontsize=fontsize, ha="center", va="center"
            )
            fig.canvas.draw()  # needed to compute bounding box
            bbox = txt.get_window_extent(renderer=fig.canvas.get_renderer())
            if bbox.width <= resolution.width and bbox.height <= resolution.height:
                break
            txt.remove()  # remove and try smaller
            fontsize -= 1

        result_path = os.path.join(self.OUTPUT_DIR, f"{uuid.uuid4()}.png")
        plt.savefig(result_path, dpi=dpi)
        plt.close(fig)

        return LatexResult(MediaFile(id=id, path=result_path), alt=latex_code)

    async def get_images(
        self,
        latex_codes: list[str],
        resolution: Resolution,
    ) -> list[LatexResult]:
        results = []
        for i, latex_code in enumerate(latex_codes):
            results.append(
                self.render_single(
                    id=i,
                    latex_code=latex_code,
                    resolution=resolution,
                )
            )

        return results

    async def get_reel_images(
        self,
        reel: Reel,
        resolution: Resolution,
    ) -> list[LatexResult]:

        latex_codes = []

        for block in reel.blocks:
            if block.media:
                if block.media.type == "latex":
                    latex_codes.append(block.media.code)

        results = await self.get_images(latex_codes=latex_codes, resolution=resolution)

        return results
