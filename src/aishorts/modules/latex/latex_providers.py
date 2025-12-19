from aishorts.modules.provider import Provider, MediaFile
from abc import abstractmethod
from dataclasses import dataclass
import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import uuid
from aishorts.modules.script.script import Reel
import subprocess
import tempfile
from PIL import Image


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


class Matplotlib(LatexProvider):
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

    def get_reel_images(
        self,
        reel: Reel,
        resolution: Resolution,
    ) -> list[LatexResult]:

        latex_codes = []

        for block in reel.blocks:
            if block.media:
                if block.media.type == "latex":
                    latex_codes.append(block.media.code)

        results = self.get_images(latex_codes=latex_codes, resolution=resolution)

        return results


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

            # Compile LaTeX → PDF
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", tex_path],
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

            return LatexResult(
                media=MediaFile(id=id, path=out_path),
                alt=latex_code,
            )

    def get_images(
        self,
        latex_codes: list[str],
        resolution: Resolution,
    ) -> list[LatexResult]:
        results = []
        for i, code in enumerate(latex_codes):
            try:
                results.append(self._render_single(i, code, resolution))
            except Exception as e:
                print(f"Failed to render LaTeX code {i}: {e}")
                # Return a placeholder or re-raise depending on your needs
                raise
        return results

    def get_reel_images(
        self,
        reel: Reel,
        resolution: Resolution,
    ) -> list[LatexResult]:
        latex_codes = []
        for block in reel.blocks:
            if block.media and block.media.type == "latex":
                latex_codes.append(block.media.code)
        return self.get_images(latex_codes, resolution)
