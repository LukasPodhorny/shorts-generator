from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio
import os
import shutil
import uuid
import aiohttp
from typing import List, Union, Dict, Optional, ClassVar
from pathlib import Path
from aishorts.utils.r2_handler import download_from_url
from aishorts.modules.provider import Provider


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


class MotionGraphicRenderer(Provider):
    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()

    @abstractmethod
    async def render(self, graphic: MotionGraphic, output_filename: str) -> str:
        """Renders the graphic and returns the local path to the video."""
        pass


class LocalMotionGraphicRenderer(MotionGraphicRenderer):
    provider_name = "local"

    async def _render_worker(
        self, queue, browser, html_content, update_fn_factory, output_dir
    ):
        from playwright.async_api import async_playwright

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
                path=os.path.join(output_dir, f"frame_{frame:04d}.png"),
                omit_background=True,
            )

            if frame % 30 == 0:
                print(f"Rendered frame {frame}")

        await page.close()

    async def render(self, graphic: MotionGraphic, output_filename: str) -> str:
        from playwright.async_api import async_playwright

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

        return output_filename


class ModalMotionGraphicRenderer(MotionGraphicRenderer):
    provider_name = "modal"

    def __init__(
        self,
        endpoint_url: str | None = None,
        modal_api_key: str | None = None,
        config: RenderConfig = None,
        **kwargs,
    ):
        super().__init__(config)
        self.endpoint_url = endpoint_url or os.getenv(
            "MODAL_MOTION_GRAPHIC_ENDPOINT_URL"
        )
        self.modal_api_key = modal_api_key or os.getenv("MODAL_API_KEY")

    async def render(self, graphic: MotionGraphic, output_filename: str) -> str:
        if not self.endpoint_url:
            raise ValueError("MODAL_MOTION_GRAPHIC_ENDPOINT_URL not set")

        total_frames = int(graphic.get_total_duration() * self.config.fps)

        # Determine the update function name and arguments
        # For BasicQuestion, it's updateFrame(time, typingDuration, thinkingDuration, answerDuration)
        if hasattr(graphic, "typing_duration"):
            params = {
                "typing_duration": graphic.typing_duration,
                "thinking_duration": graphic.thinking_duration,
                "answer_duration": graphic.answer_duration,
            }
            update_fn_template = "updateFrame({time}, {typing_duration}, {thinking_duration}, {answer_duration})"
        else:
            # Fallback for other potential motion graphics
            params = {}
            update_fn_template = "updateFrame({time})"

        payload = {
            "html": graphic.get_html(),
            "total_frames": total_frames,
            "update_fn_template": update_fn_template,
            "params": params,
            "width": self.config.width,
            "height": self.config.height,
            "fps": self.config.fps,
            "output_key": f"motion_graphic/{os.path.basename(output_filename)}",
        }

        if self.modal_api_key:
            payload["api_key"] = self.modal_api_key

        print(
            f"Sending motion graphic render job to Modal.com ({total_frames} frames)..."
        )
        print(f"DEBUG: Payload keys: {list(payload.keys())}")
        print(f"DEBUG: update_fn_template: {payload.get('update_fn_template')}")
        print(f"DEBUG: params: {payload.get('params')}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url, json=payload, timeout=600
            ) as response:
                if not response.ok:
                    text = await response.text()
                    raise Exception(
                        f"Modal Motion Graphic failed with {response.status}: {text}"
                    )

                result = await response.json()

        download_url = result.get("download_url")

        # Download locally
        await download_from_url(download_url, full_path=output_filename)

        return output_filename
