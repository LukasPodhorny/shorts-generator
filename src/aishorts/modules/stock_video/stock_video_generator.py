import asyncio
import logging
from pathlib import Path

from aishorts.modules.script.script import AssetType, Reel
from aishorts.modules.stock_video.stock_video_providers import StockVideoProvider
from aishorts.utils.r2_handler import CloudflareR2

logger = logging.getLogger("ShortsGenerator.StockVideo")


class StockVideoGenerator:
    def __init__(self, provider="auto", orientation="landscape", upload=True,
                 output_dir="output/stock_video", max_concurrent=2,
                 failure_mode="fallback", **kwargs):
        if failure_mode not in {"fallback", "error"}:
            raise ValueError("stock_video failure_mode must be fallback or error")
        self.provider = StockVideoProvider.get(provider)(**kwargs)
        self.orientation = orientation
        self.upload = upload
        self.output_dir = Path(output_dir)
        self.failure_mode = failure_mode
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def populate_reel(self, reel: Reel, **kwargs):
        used_sources: set[str] = set()

        async def populate(block, media):
            async with self.semaphore:
                try:
                    result = await self.provider.get_clip(
                        media.keywords, self.orientation, self.output_dir, used_sources
                    )
                    if result is None:
                        raise LookupError(f"No unused stock footage for {media.keywords!r}")
                except Exception as exc:
                    if self.failure_mode == "error":
                        raise
                    logger.warning("Stock footage unavailable; using teaching slide: %s", exc)
                    return
                block.assets.media_map[media.id] = result.path
                block.assets.media_attributions[media.id] = result.attribution
                if self.upload:
                    # Only managed copies enter the checkpoint, never permanent library paths.
                    url = await asyncio.to_thread(CloudflareR2().upload_file, result.path, f"stock_video/{Path(result.path).name}")
                    block.assets.media_url_map[media.id] = url

        await asyncio.gather(*(
            populate(block, media)
            for block in reel.blocks if AssetType.STOCK_VIDEO in block.valid_assets
            for media in block.media if media.type == "stock_video"
        ))
        return reel
