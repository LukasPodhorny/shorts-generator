from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright
import shutil
import uuid


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    output_dir: str = "animated_frames"
    concurrency: int = 4


class MotionGraphic(ABC):
    @abstractmethod
    def get_html(self) -> str:
        """Returns the full HTML content to be rendered."""
        pass

    @abstractmethod
    def get_total_duration(self) -> float:
        """Returns total duration in seconds."""
        pass

    @abstractmethod
    def get_javascript_update_call(self, time_passed: float) -> str:
        """Returns the JS function call to update the frame for a given time."""
        pass


class MotionGraphicRenderer:
    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()

    async def _render_worker(
        self, queue, browser, html_content, update_fn_factory, output_dir
    ):
        page = await browser.new_page(
            viewport={"width": self.config.width, "height": self.config.height}
        )
        await page.set_content(html_content, timeout=60000)

        while True:
            try:
                frame = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            time_passed = frame / self.config.fps
            js_call = update_fn_factory(time_passed)

            await page.evaluate(js_call)
            await page.screenshot(
                path=f"{output_dir}/frame_{frame:04d}.png",
                omit_background=True,
            )

            if frame % 30 == 0:
                print(f"Rendered frame {frame}")

        await page.close()

    async def render(self, graphic: MotionGraphic, output_filename: str):
        # Create unique output directory for this render to avoid collisions
        job_output_dir = os.path.join(self.config.output_dir, str(uuid.uuid4()))
        os.makedirs(job_output_dir, exist_ok=True)

        total_frames = int(graphic.get_total_duration() * self.config.fps)
        queue = asyncio.Queue()
        for frame in range(total_frames):
            queue.put_nowait(frame)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            tasks = []
            html_content = graphic.get_html()
            update_fn = graphic.get_javascript_update_call

            for _ in range(self.config.concurrency):
                tasks.append(
                    asyncio.create_task(
                        self._render_worker(
                            queue, browser, html_content, update_fn, job_output_dir
                        )
                    )
                )
            await asyncio.gather(*tasks)
            await browser.close()

        print("Stitching frames...")
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-framerate",
            str(self.config.fps),
            "-i",
            f"{job_output_dir}/frame_%04d.png",
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            output_filename,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()

        # Cleanup frames
        if os.path.exists(job_output_dir):
            shutil.rmtree(job_output_dir)
