import uuid
import os
import asyncio
from aishorts.modules.video_edit.video_edit import VideoTemplate
from aishorts.modules.script.script import Reel, AssetType
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.ffmpeg_providers import FFmpegProvider, FFmpegResult
from aishorts.utils.r2_handler import download_from_url


class VideoGenerator:

    def __init__(
        self, video_template: VideoTemplate, provider: str = "modal_ffmpeg", **kwargs
    ):
        self.template_config = video_template.template_config
        edit_template = video_template.edit_template.lower()

        edit_cls = EditTemplate.get(edit_template)
        if not edit_cls:
            raise ValueError(f"Unknown video template class '{provider}'")

        self.edit = edit_cls(self.template_config, **kwargs)

        render_cls = FFmpegProvider.get(provider)
        if not render_cls:
            raise ValueError(f"Unknown video template class '{provider}'")

        self.render = render_cls(**kwargs)

    async def _ensure_assets_local(self, reel: Reel):
        """
        Check if all assets referred to in the reel are present on the local filesystem.
        If missing but a URL is available, re-download from R2.
        This is crucial when resuming from a checkpoint on a new environment (like Railway).
        """
        download_tasks = []

        for block in reel.blocks:
            assets = block.assets
            if not assets:
                continue

            # 1. Voice
            if assets.voice_filepath and not os.path.exists(assets.voice_filepath):
                if assets.voice_url:
                    print(f"File missing: {assets.voice_filepath}. Re-downloading from {assets.voice_url}")
                    os.makedirs(os.path.dirname(assets.voice_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(assets.voice_url, full_path=assets.voice_filepath))
                else:
                    print(f"WARNING: File missing and no URL for voice_filepath: {assets.voice_filepath}")

            # 2. Lipsync
            if assets.lipsync_filepath and not os.path.exists(assets.lipsync_filepath):
                if assets.lipsync_url:
                    print(f"File missing: {assets.lipsync_filepath}. Re-downloading from {assets.lipsync_url}")
                    os.makedirs(os.path.dirname(assets.lipsync_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(assets.lipsync_url, full_path=assets.lipsync_filepath))
                else:
                    print(f"WARNING: File missing and no URL for lipsync_filepath: {assets.lipsync_filepath}")

            # 3. StaticFace
            if assets.staticface_filepath and not os.path.exists(assets.staticface_filepath):
                if assets.staticface_url:
                    print(f"File missing: {assets.staticface_filepath}. Re-downloading from {assets.staticface_url}")
                    os.makedirs(os.path.dirname(assets.staticface_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(assets.staticface_url, full_path=assets.staticface_filepath))
                else:
                    print(f"WARNING: File missing and no URL for staticface_filepath: {assets.staticface_filepath}")

            # 4. Song
            if assets.song_filepath and not os.path.exists(assets.song_filepath):
                if assets.song_url:
                    print(f"File missing: {assets.song_filepath}. Re-downloading from {assets.song_url}")
                    os.makedirs(os.path.dirname(assets.song_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(assets.song_url, full_path=assets.song_filepath))
                else:
                    print(f"WARNING: File missing and no URL for song_filepath: {assets.song_filepath}")

            # 5. Media Map (Images, LaTeX, Manim)
            for media_id, filepath in assets.media_map.items():
                if filepath and not os.path.exists(filepath):
                    url = assets.media_url_map.get(media_id)
                    if url:
                        print(f"File missing: {filepath}. Re-downloading from {url}")
                        os.makedirs(os.path.dirname(filepath), exist_ok=True)
                        download_tasks.append(download_from_url(url, full_path=filepath))
                    else:
                        print(f"WARNING: File missing and no URL for media {media_id}: {filepath}")

        if download_tasks:
            await asyncio.gather(*download_tasks)

    async def compose(self, reel: Reel, **kwargs) -> FFmpegResult:
        await self._ensure_assets_local(reel)
        cmd = self.edit.compose(reel=reel, **kwargs)

        return await self.render.render(cmd, f"{uuid.uuid4()}.mp4", **kwargs)
