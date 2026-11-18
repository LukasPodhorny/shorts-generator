import os
import uuid
from abc import abstractmethod
from pathlib import Path

import aiohttp

from aishorts.modules.provider import Provider
from aishorts.modules.script.script import SlideMedia
from aishorts.modules.slides.renderer import render_slide
from aishorts.modules.slides.style import SlideRenderConfig


class SlideProvider(Provider):
    @abstractmethod
    def render(self, slide: SlideMedia, config: SlideRenderConfig, output: Path):
        """Write a PNG to output. Providers may implement this asynchronously."""


class PillowSlides(SlideProvider):
    provider_name = "pillow"

    def __init__(self, **kwargs):
        pass

    def render(self, slide, config, output):
        return render_slide(slide, config, output)


class ModalSlides(SlideProvider):
    provider_name = "modal_slides"

    def __init__(self, endpoint_url=None, api_key=None, timeout=60, **kwargs):
        self.endpoint_url = endpoint_url or os.getenv("MODAL_SLIDES_ENDPOINT_URL")
        self.api_key = api_key or os.getenv("MODAL_SLIDES_API_KEY")
        self.timeout = timeout
        if not self.endpoint_url or not self.api_key:
            raise ValueError("modal_slides requires MODAL_SLIDES_ENDPOINT_URL and MODAL_SLIDES_API_KEY")

    async def render(self, slide, config, output):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            async with session.post(
                self.endpoint_url,
                json={"slide": slide.model_dump(), "config": config.model_dump()},
                headers={"Authorization": f"Bearer {self.api_key}"},
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.content_type != "image/png":
                    raise ValueError("Slide service returned a non-PNG response")
                output.parent.mkdir(parents=True, exist_ok=True)
                temporary = output.with_suffix(f".{uuid.uuid4().hex}.part")
                try:
                    size = 0
                    with temporary.open("wb") as stream:
                        async for chunk in response.content.iter_chunked(65536):
                            size += len(chunk)
                            if size > 20 * 1024 * 1024:
                                raise ValueError("Slide service response exceeds 20 MiB")
                            stream.write(chunk)
                    from PIL import Image
                    with Image.open(temporary) as image:
                        if image.format != "PNG":
                            raise ValueError("Slide service returned a non-PNG image")
                        if image.size != (config.width, config.height):
                            raise ValueError("Slide service returned incorrect dimensions")
                        image.verify()
                    temporary.replace(output)
                finally:
                    temporary.unlink(missing_ok=True)
        return str(output)
