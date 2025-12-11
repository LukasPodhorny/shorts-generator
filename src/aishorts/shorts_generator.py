import asyncio
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from dataclasses import dataclass, field
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.video_edit.video_edit import VideoTemplate, TemplateAssets
from aishorts.modules.video_edit.video_generator import VideoGenerator
from aishorts.modules.avatar import Avatar
from aishorts.modules.video_edit.video_edit_templates import *
from aishorts.utils.registry import EDIT_TEMPLATES
from aishorts.modules.video_edit.asset_type import AssetType
from importlib.resources import read_text
from pydantic import BaseModel, Field


class ScriptConfig(BaseModel):
    """
    Changing base_instructions can cause errors if not done properly.
    """

    base_instructions: str | None = Field(
        default_factory=lambda: read_text(
            "aishorts.resources", "base_instructions_default.txt"
        )
    )
    provider: str | None = "chatgpt"
    generate_latex: bool = False
    generate_image: bool = False
    provider_config: dict = Field(default_factory=dict)


@dataclass
class SubtitleConfig:
    provider: str = "elevenlabs"
    provider_config: dict = field(default_factory=dict)


@dataclass
class ShortsConfig:
    avatars: list[Avatar]
    video_template: VideoTemplate
    script_config: ScriptConfig = field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = field(default_factory=SubtitleConfig)


class ShortsGenerator:
    def __init__(
        self,
        shorts_config: ShortsConfig,
        tts_api_key: str | None = None,
        lipsync_api_key: str | None = None,
        subtitles_api_key: str | None = None,
        llm_api_key: str | None = None,
    ):
        self.avatars = shorts_config.avatars

        self.script_gen = ScriptGenerator(
            base_instructions=shorts_config.script_config.base_instructions,
            avatars=self.avatars,
            generate_latex=shorts_config.script_config.generate_latex,
            generate_image=shorts_config.script_config.generate_image,
            provider=shorts_config.script_config.provider,
            api_key=llm_api_key,
            **shorts_config.script_config.provider_config,
        )

        self.voice_gen = VoiceGenerator(avatars=self.avatars, api_key=tts_api_key)

        self.lipsync_gen = LipsyncGenerator(
            avatars=self.avatars, api_key=lipsync_api_key
        )

        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config,
            api_key=subtitles_api_key,
        )

        self.video_gen = VideoGenerator(video_template=shorts_config.video_template)

        self.video_template = shorts_config.video_template

    async def generate_shorts_async(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
    ):
        required_assets = EDIT_TEMPLATES.get(
            self.video_template.edit_template.lower()
        ).required_assets

        template_assets = [TemplateAssets() for _ in range(amount)]

        print("\n\n Generating scripts...")
        if AssetType.SCRIPT in required_assets:
            reel_series = await self.script_gen.generate_script(
                num_reels=amount, files=files, user_input=user_input
            )

            for asset, result in zip(template_assets, reel_series.reels):
                asset.reel_script = result

        print("Generating voiceover...")
        if AssetType.VOICE in required_assets:
            tasks = [
                self.voice_gen.generate_reel_dialogues(reel)
                for reel in reel_series.reels
            ]
            results = await asyncio.gather(*tasks)

            for asset, result in zip(template_assets, results):
                asset.voiceovers = result

        print("Generating lipsync video and subtitles...")
        tasks = []
        if AssetType.LIPSYNC in required_assets:
            lipsync_tasks = [
                self.lipsync_gen.generate_lipsyncs(asset.voiceovers)
                for asset in template_assets
            ]
            tasks.extend(lipsync_tasks)

        if AssetType.SUBTITLES in required_assets:
            subtitle_tasks = [
                self.subtitle_gen.generate_multiple_subtitles(asset.voiceovers)
                for asset in template_assets
            ]
            tasks.extend(subtitle_tasks)

        results = await asyncio.gather(*tasks)

        # Map results back
        idx = 0
        if AssetType.LIPSYNC in required_assets:
            for asset, result in zip(template_assets, results[idx]):
                asset.lipsync_videos = result
            idx += 1
        if AssetType.SUBTITLES in required_assets:
            for asset, result in zip(template_assets, results[idx]):
                asset.subtitles = result
            idx += 1

        print("Generating final video...")
        return self.video_gen.compose(template_assets=template_assets)

    def generate_shorts(
        self,
        files: list[str] | None = None,
        user_input: str | None = None,
    ):
        asyncio.run(
            self.generate_shorts_async(
                files=files,
                user_input=user_input,
            ),
        )
