import asyncio
import uuid
from pathlib import Path

from aishorts.modules.script.script import AssetType, Reel, SlideMedia
from aishorts.modules.slides.slide_providers import SlideProvider
from aishorts.modules.slides.style import SlideRenderConfig
from aishorts.utils.async_utils import await_or_thread
from aishorts.utils.r2_handler import CloudflareR2


class SlideGenerator:
    """Render after primary media, preserving the usual local/remote asset pair."""

    def __init__(self, provider="pillow", render_config=None, upload=True,
                 output_dir="output/slides", max_concurrent=3, **kwargs):
        self.provider = SlideProvider.get(provider)(**kwargs)
        self.render_config = render_config or SlideRenderConfig()
        self.upload = upload
        self.output_dir = Path(output_dir)
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def populate_reel(self, reel: Reel, **kwargs):
        async def render(block, slide, index):
            async with self.semaphore:
                visuals = [m for m in block.media if m.type != "slide" and (
                    m.id in block.assets.media_map or m.id in block.assets.media_url_map
                )]
                credits = list(dict.fromkeys(
                    f"{a.creator} / {a.provider}"
                    for m in visuals
                    if (a := block.assets.media_attributions.get(m.id)) is not None
                ))
                config = self.render_config.model_copy(update={
                    "has_visual": bool(visuals), "chapter": index + 1,
                    "chapters": len(reel.blocks), "attribution": " · ".join(credits)[:180],
                })
                path = self.output_dir / f"{uuid.uuid4().hex}.png"
                await await_or_thread(self.provider.render, slide, config, path)
                block.assets.media_map[slide.id] = str(path)
                if self.upload:
                    url = await asyncio.to_thread(CloudflareR2().upload_file, str(path), f"slides/{path.name}")
                    block.assets.media_url_map[slide.id] = url

        tasks = []
        for i, block in enumerate(reel.blocks):
            if AssetType.SLIDES in block.valid_assets:
                for media in block.media:
                    if isinstance(media, SlideMedia):
                        tasks.append(render(block, media, i))
        await asyncio.gather(*tasks)
        return reel
