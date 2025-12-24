import asyncio
import logging
import os
import pickle
from datetime import datetime
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from aishorts.modules.video_edit.video_generator import VideoGenerator
from dataclasses import dataclass, field
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.video_edit.video_edit import VideoTemplate, TemplateAssets
from aishorts.modules.avatar import Avatar
from aishorts.modules.video_edit.video_edit_templates import *
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.video_edit.video_edit import AssetType
from importlib.resources import read_text
from pydantic import BaseModel, Field
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.utils.image_utils import ImageStyle
from aishorts.modules.latex.latex_generator import LatexGenerator
from aishorts.modules.script.llm_providers import ReelSeries
from pathlib import Path


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
    provider_config: dict = Field(default_factory=dict)


class ImagesConfig(BaseModel):
    provider: str = "unsplash"
    provider_config: dict = field(default_factory=dict)


class LatexConfig(BaseModel):
    provider: str = "real_latex"
    provider_config: dict = field(default_factory=dict)


class SubtitleConfig(BaseModel):
    provider: str = "elevenlabs"
    provider_config: dict = field(default_factory=dict)


class ShortsConfig(BaseModel):
    avatars: list[Avatar]
    video_template: VideoTemplate
    script_config: ScriptConfig = field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = field(default_factory=SubtitleConfig)
    images_config: ImagesConfig = field(default_factory=ImagesConfig)
    latex_config: LatexConfig = field(default_factory=LatexConfig)


class ShortsGenerator:
    def __init__(
        self,
        shorts_config: ShortsConfig,
        tts_api_key: str | None = None,
        lipsync_api_key: str | None = None,
        subtitles_api_key: str | None = None,
        llm_api_key: str | None = None,
    ):
        self._setup_logging()

        self.tts_api_key = tts_api_key
        self.lipsync_api_key = lipsync_api_key
        self.subtitles_api_key = subtitles_api_key
        self.llm_api_key = llm_api_key

        self.update_config(shorts_config)

    def update_config(self, shorts_config: ShortsConfig):
        self.avatars = shorts_config.avatars
        self.video_template = shorts_config.video_template
        self.template_config = self.video_template.template_config

        self.required_assets = EditTemplate.get(
            self.video_template.edit_template.lower()
        ).required_assets

        self.image_gen = ImageGenerator(
            provider=shorts_config.images_config.provider,
            max_width=self.template_config.max_image_width,
            max_height=self.template_config.max_image_height,
            image_style=self.template_config.image_style,
            **shorts_config.images_config.provider_config,
        )

        self.latex_gen = LatexGenerator(
            provider=shorts_config.latex_config.provider,
            width=self.template_config.latex_width,
            height=self.template_config.latex_height,
            image_style=self.template_config.latex_style,
            **shorts_config.latex_config.provider_config,
        )

        self.script_gen = ScriptGenerator(
            base_instructions=shorts_config.script_config.base_instructions,
            avatars=self.avatars,
            generate_latex=AssetType.LATEX in self.required_assets,
            generate_image=AssetType.IMAGES in self.required_assets,
            provider=shorts_config.script_config.provider,
            api_key=self.llm_api_key,
            **shorts_config.script_config.provider_config,
        )

        self.voice_gen = VoiceGenerator(
            avatars=self.avatars,
            api_key=self.tts_api_key,
        )

        self.lipsync_gen = LipsyncGenerator(
            avatars=self.avatars, api_key=self.lipsync_api_key
        )

        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config,
            api_key=self.subtitles_api_key,
        )

        self.video_gen = VideoGenerator(video_template=shorts_config.video_template)

    def _setup_logging(self):
        self.logger = logging.getLogger("ShortsGenerator")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            os.makedirs("logs", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # File Handler
            fh = logging.FileHandler(f"logs/run_{timestamp}.log")
            fh.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            self.logger.addHandler(fh)

            # Stream Handler (console output)
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(sh)

    def _save_debug_state(self, assets: list[TemplateAssets], stage: str):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"logs/assets_{stage}_{timestamp}.pkl"
            with open(filepath, "wb") as f:
                pickle.dump(assets, f)
            self.logger.info(f"Saved checkpoint: {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")

    def _apply_results(self, template_assets, tasks_map, results):
        attr_map = {
            AssetType.LATEX: "latex",
            AssetType.IMAGES: "images",
            AssetType.VOICE: "voiceovers",
            AssetType.LIPSYNC: "lipsync_videos",
            AssetType.SUBTITLES: "subtitles",
        }

        for asset_type, batch_result in zip(tasks_map.keys(), results):
            if attr_name := attr_map.get(asset_type):
                for asset, res in zip(template_assets, batch_result):
                    setattr(asset, attr_name, res)

    async def generate_shorts_async(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
    ) -> list[str]:

        template_assets = [TemplateAssets() for _ in range(amount)]

        # Script
        self.logger.info("\n\n Generating scripts...")
        if AssetType.SCRIPT in self.required_assets:
            # reel_series = await self.script_gen.generate_script(
            #    num_reels=amount, files=files, user_input=user_input
            # )

            reel_json = Path("tests/test_configs/mock_script.json").read_text()
            reel_series = ReelSeries.model_validate_json(reel_json)

            for asset, result in zip(template_assets, reel_series.reels):
                asset.reel_script = result

            self._save_debug_state(template_assets, "script")

        # TTS, Images, LaTex
        self.logger.info("Generating voiceover, images, latex...")
        tasks_map = {}

        if AssetType.VOICE in self.required_assets:
            tasks_map[AssetType.VOICE] = asyncio.gather(
                *[
                    self.voice_gen.generate_reel_dialogues(reel)
                    for reel in reel_series.reels
                ]
            )

        if AssetType.IMAGES in self.required_assets:
            tasks_map[AssetType.IMAGES] = asyncio.gather(
                *[self.image_gen.get_reel_images(reel) for reel in reel_series.reels]
            )

        if AssetType.LATEX in self.required_assets:
            tasks_map[AssetType.LATEX] = asyncio.gather(
                *[self.latex_gen.get_reel_images(reel) for reel in reel_series.reels]
            )

        if tasks_map:
            results = await asyncio.gather(*tasks_map.values())
            self._apply_results(template_assets, tasks_map, results)
            self._save_debug_state(template_assets, "media")

        # Lipsync, Subtitles
        self.logger.info("Generating lipsync video and subtitles...")
        tasks_map_2 = {}

        if AssetType.LIPSYNC in self.required_assets:
            tasks_map_2[AssetType.LIPSYNC] = asyncio.gather(
                *[
                    self.lipsync_gen.generate_lipsyncs(asset.voiceovers)
                    for asset in template_assets
                ]
            )

        if AssetType.SUBTITLES in self.required_assets:
            tasks_map_2[AssetType.SUBTITLES] = asyncio.gather(
                *[
                    self.subtitle_gen.generate_multiple_subtitles(asset.voiceovers)
                    for asset in template_assets
                ]
            )

        if tasks_map_2:
            results = await asyncio.gather(*tasks_map_2.values())
            self._apply_results(template_assets, tasks_map_2, results)
            self._save_debug_state(template_assets, "lipsync_subs")

        # Video Edit
        self.logger.info(f"Assets: {template_assets}")
        self.logger.info("Generating final video...")
        results = []
        for asset in template_assets:
            results.append(self.video_gen.compose(template_assets=asset))

        return results

    def generate_shorts(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
    ) -> list[str]:
        asyncio.run(
            self.generate_shorts_async(
                amount=amount,
                files=files,
                user_input=user_input,
            ),
        )
