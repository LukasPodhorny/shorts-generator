from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import uuid
from aishorts.modules.script.script import Reel, AssetType
import subprocess
import tempfile
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg


from aishorts.utils.r2_handler import download_from_url, CloudflareR2

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

    def __init__(self, **kwargs):
        self.r2 = CloudflareR2()

    @abstractmethod
    def populate_reel(self, reel: Reel, resolution: Resolution, **kwargs) -> None:
        pass


class Matplotlib(LatexProvider):
    provider_name = "matplotlib"

    def render_single(self, id: int, latex_code: str, resolution: Resolution):
        # ... (keep existing render_single logic)
        dpi = 100
        fig = Figure(figsize=(resolution.width / dpi, resolution.height / dpi), dpi=dpi)
        FigureCanvasAgg(fig)
        fig.patch.set_facecolor("white")

        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        fontsize = min(resolution.width, resolution.height) // 5
        while fontsize > 1:
            txt = ax.text(
                0.5, 0.5, f"${latex_code}$", fontsize=fontsize, ha="center", va="center"
            )
            fig.canvas.draw()
            bbox = txt.get_window_extent(renderer=fig.canvas.get_renderer())
            if bbox.width <= resolution.width and bbox.height <= resolution.height:
                break
            txt.remove()
            fontsize -= 1

        result_path = os.path.join(self.OUTPUT_DIR, f"{uuid.uuid4()}.png")
        fig.savefig(result_path, dpi=dpi)

        # Upload to R2
        remote_key = f"latex/{os.path.basename(result_path)}"
        url = self.r2.upload_file(result_path, remote_key)

        return LatexResult(MediaFile(id=id, path=result_path, url=url), alt=latex_code)

    def get_images(
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

    def populate_reel(
        self,
        reel: Reel,
        resolution: Resolution,
    ) -> None:

        latex_codes = []
        ids = []

        for i, block in enumerate(reel.blocks):
            if AssetType.LATEX in block.valid_assets and block.media:
                for media_item in block.media:
                    if media_item.type == "latex":
                        latex_codes.append(media_item.code)
                        ids.append((i, media_item.id))

        results = self.get_images(latex_codes=latex_codes, resolution=resolution)

        for res, (block_id, media_id) in zip(results, ids):
            reel.blocks[block_id].assets.media_map[media_id] = res.media.path
            reel.blocks[block_id].assets.media_url_map[media_id] = res.media.url


class RealLatex(LatexProvider):
    provider_name = "real_latex"

    # Standalone document class with geometry for tight fitting
    LATEX_TEMPLATE = r"""
    \documentclass[preview,border=10pt]{standalone}
    \usepackage{amsmath}
    \usepackage{amssymb}
    \usepackage{amsfonts}
    \usepackage{chemfig}
    \usepackage[version=4]{mhchem}
    \usepackage{xcolor}
    \begin{document}
    \Huge
    \mbox{$\displaystyle %s$}
    \end{document}
    """

    def _render_single(
        self, id: int, latex_code: str, resolution: Resolution
    ) -> LatexResult:
        with tempfile.TemporaryDirectory() as tmp:
            tex_path = os.path.join(tmp, "eq.tex")
            pdf_path = os.path.join(tmp, "eq.pdf")
            png_base = os.path.join(tmp, "eq")

            # Write LaTeX file
            latex_content = self.LATEX_TEMPLATE % latex_code
            with open(tex_path, "w") as f:
                f.write(latex_content)

            # Compile LaTeX -> PDF.
            # The LaTeX body is LLM-generated from (potentially attacker-
            # influenced) user input, so harden the compile:
            #   -no-shell-escape disables \write18 shell execution
            #   -interaction=nonstopmode avoids hanging on prompts
            # Note: \input/\openin can still read files, so the LaTeX is run in
            # an isolated tmp dir with no sensitive contents.
            result = subprocess.run(
                [
                    "pdflatex",
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    tex_path,
                ],
                cwd=tmp,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if result.returncode != 0 or not os.path.exists(pdf_path):
                # Read the log file for more details
                log_path = os.path.join(tmp, "eq.log")
                error_msg = f"LaTeX compilation failed for: {latex_code}\n"
                error_msg += f"\nGenerated LaTeX:\n{latex_content}\n"
                if os.path.exists(log_path):
                    with open(log_path, "r") as log_file:
                        log_content = log_file.read()
                        error_msg += f"\nLast 2000 chars of log:\n{log_content[-2000:]}"
                else:
                    error_msg += f"\nstdout: {result.stdout.decode()}\nstderr: {result.stderr.decode()}"
                raise RuntimeError(error_msg)

            # Calculate optimal DPI to fill resolution
            # First render at moderate DPI to get dimensions
            subprocess.run(
                [
                    "pdftocairo",
                    "-png",
                    "-singlefile",
                    "-r",
                    "300",
                    pdf_path,
                    png_base,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Load to get natural size
            temp_img = Image.open(png_base + ".png")
            natural_w, natural_h = temp_img.size
            temp_img.close()
            os.remove(png_base + ".png")

            # Calculate DPI needed to fill target resolution
            # We want to maximize size while fitting in the resolution
            scale_w = resolution.width / natural_w
            scale_h = resolution.height / natural_h
            scale = min(scale_w, scale_h)

            # Target DPI (base 300 * scale factor, capped at reasonable values)
            target_dpi = int(300 * scale * 0.95)  # 0.95 to leave small margin
            target_dpi = max(150, min(target_dpi, 2400))  # Reasonable bounds

            # Render at optimal DPI
            subprocess.run(
                [
                    "pdftocairo",
                    "-png",
                    "-singlefile",
                    "-r",
                    str(target_dpi),
                    pdf_path,
                    png_base,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Load and center on target resolution
            img = Image.open(png_base + ".png").convert("RGBA")
            img_w, img_h = img.size

            # If still larger than resolution, scale down
            if img_w > resolution.width or img_h > resolution.height:
                scale = min(
                    resolution.width / img_w,
                    resolution.height / img_h,
                )
                new_size = (
                    int(img_w * scale),
                    int(img_h * scale),
                )
                img = img.resize(new_size, Image.LANCZOS)
                img_w, img_h = new_size

            # Create white background and center the equation
            final_img = Image.new(
                "RGBA",
                (resolution.width, resolution.height),
                (255, 255, 255, 255),
            )

            offset = (
                (resolution.width - img_w) // 2,
                (resolution.height - img_h) // 2,
            )
            final_img.paste(img, offset, img)

            # Save result
            out_path = os.path.join(self.OUTPUT_DIR, f"{uuid.uuid4()}.png")
            final_img.save(out_path)

            # Upload to R2
            remote_key = f"latex/{os.path.basename(out_path)}"
            url = self.r2.upload_file(out_path, remote_key)

            return LatexResult(
                media=MediaFile(id=id, path=out_path, url=url),
                alt=latex_code,
            )

    def get_images(
        self,
        latex_codes: list[str],
        resolution: Resolution,
    ) -> list[LatexResult]:
        def _render_task(args):
            i, code = args
            try:
                return self._render_single(i, code, resolution)
            except Exception as e:
                print(f"Failed to render LaTeX code {i}: {e}")
                raise

        # Parallelize rendering of equations within the reel
        with ThreadPoolExecutor() as executor:
            results = list(executor.map(_render_task, enumerate(latex_codes)))

        return results

    def populate_reel(
        self,
        reel: Reel,
        resolution: Resolution,
    ) -> None:
        latex_codes = []
        ids = []
        for i, block in enumerate(reel.blocks):
            if AssetType.LATEX in block.valid_assets and block.media:
                for media_item in block.media:
                    if media_item.type == "latex":
                        latex_codes.append(media_item.code)
                        ids.append((i, media_item.id))

        results = self.get_images(latex_codes, resolution)
        for res, (block_id, media_id) in zip(results, ids):
            reel.blocks[block_id].assets.media_map[media_id] = res.media.path
            reel.blocks[block_id].assets.media_url_map[media_id] = res.media.url
