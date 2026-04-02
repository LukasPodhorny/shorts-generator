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
        self,
        video_template: VideoTemplate,
        provider: str = "modal_ffmpeg",
        download_results: bool = False,
        **kwargs,
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

        self.render = render_cls(download_results=download_results, **kwargs)

    async def ensure_assets_local(self, reel: Reel):
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
            voice_filepath = getattr(assets, "voice_filepath", None)
            voice_url = getattr(assets, "voice_url", None)
            if voice_filepath and not os.path.exists(voice_filepath):
                if voice_url:
                    print(f"File missing: {voice_filepath}. Re-downloading from {voice_url}")
                    os.makedirs(os.path.dirname(voice_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(voice_url, full_path=voice_filepath))
                else:
                    print(f"WARNING: File missing and no URL for voice_filepath: {voice_filepath}")

            # 2. Lipsync
            lipsync_filepath = getattr(assets, "lipsync_filepath", None)
            lipsync_url = getattr(assets, "lipsync_url", None)
            if lipsync_filepath and not os.path.exists(lipsync_filepath):
                if lipsync_url:
                    print(f"File missing: {lipsync_filepath}. Re-downloading from {lipsync_url}")
                    os.makedirs(os.path.dirname(lipsync_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(lipsync_url, full_path=lipsync_filepath))
                else:
                    print(f"WARNING: File missing and no URL for lipsync_filepath: {lipsync_filepath}")

            # 3. StaticFace
            staticface_filepath = getattr(assets, "staticface_filepath", None)
            staticface_url = getattr(assets, "staticface_url", None)
            if staticface_filepath and not os.path.exists(staticface_filepath):
                if staticface_url:
                    print(f"File missing: {staticface_filepath}. Re-downloading from {staticface_url}")
                    os.makedirs(os.path.dirname(staticface_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(staticface_url, full_path=staticface_filepath))
                else:
                    print(f"WARNING: File missing and no URL for staticface_filepath: {staticface_filepath}")

            # 4. Song
            song_filepath = getattr(assets, "song_filepath", None)
            song_url = getattr(assets, "song_url", None)
            if song_filepath and not os.path.exists(song_filepath):
                if song_url:
                    print(f"File missing: {song_filepath}. Re-downloading from {song_url}")
                    os.makedirs(os.path.dirname(song_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(song_url, full_path=song_filepath))
                else:
                    print(f"WARNING: File missing and no URL for song_filepath: {song_filepath}")

            # 5. Question
            question_filepath = getattr(assets, "question_filepath", None)
            question_url = getattr(assets, "question_url", None)
            if question_filepath and not os.path.exists(question_filepath):
                if question_url:
                    print(f"File missing: {question_filepath}. Re-downloading from {question_url}")
                    os.makedirs(os.path.dirname(question_filepath), exist_ok=True)
                    download_tasks.append(download_from_url(question_url, full_path=question_filepath))
                else:
                    print(f"WARNING: File missing and no URL for question_filepath: {question_filepath}")

            # 6. Media Map (Images, LaTeX, Manim)
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
        await self.ensure_assets_local(reel)
        cmd = self.edit.compose(reel=reel, **kwargs)

        return await self.render.render(cmd, f"{uuid.uuid4()}.mp4", **kwargs)
