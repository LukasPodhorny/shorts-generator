import asyncio
import logging
import os
import pickle
from datetime import datetime
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from aishorts.modules.video_edit.video_generator import VideoGenerator
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.video_edit.video_edit import VideoTemplate
from aishorts.modules.avatar import Avatar
from aishorts.modules.video_edit.video_edit_templates import *
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.script.script import AssetType
from importlib.resources import read_text
from pydantic import BaseModel, Field
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.modules.latex.latex_generator import LatexGenerator
from aishorts.modules.script.script import ReelSeries
from aishorts.modules.question.question_generator import QuestionGenerator
from aishorts.modules.lipsync.lipsync_providers import populate_reel_static_faces
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
    provider_config: dict = Field(default_factory=dict)


class LatexConfig(BaseModel):
    provider: str = "real_latex"
    provider_config: dict = Field(default_factory=dict)


class SubtitleConfig(BaseModel):
    provider: str = "elevenlabs"
    provider_config: dict = Field(default_factory=dict)


class QuestionConfig(BaseModel):
    provider: str = "motion_graphic"
    provider_config: dict = Field(default_factory=dict)


class ShortsConfig(BaseModel):
    avatars: list[Avatar]
    video_template: VideoTemplate
    script_config: ScriptConfig = Field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = Field(default_factory=SubtitleConfig)
    images_config: ImagesConfig = Field(default_factory=ImagesConfig)
    latex_config: LatexConfig = Field(default_factory=LatexConfig)
    question_config: QuestionConfig = Field(default_factory=QuestionConfig)


class ShortsGenerator:
    def __init__(
        self,
        shorts_config: ShortsConfig,
        tts_f5tts_api_key: str | None = None,
        tts_lemonfox_api_key: str | None = None,
        lipsync_float_api_key: str | None = None,
        subtitles_api_key: str | None = None,
        llm_api_key: str | None = None,
        image_api_key: str | None = None,
    ):
        self.tts_f5tts_api_key = tts_f5tts_api_key
        self.tts_lemonfox_api_key = tts_lemonfox_api_key
        self.lipsync_float_api_key = lipsync_float_api_key
        self.subtitles_api_key = subtitles_api_key
        self.llm_api_key = llm_api_key
        self.tts_lemonfox_api_key = tts_lemonfox_api_key
        self.lipsync_float_api_key = lipsync_float_api_key
        self.subtitles_api_key = subtitles_api_key
        self.llm_api_key = llm_api_key
        self.image_api_key = image_api_key

        self._setup_logging()
        self.update_config(shorts_config)

    def update_config(self, shorts_config: ShortsConfig):
        self.avatars = shorts_config.avatars
        self.video_template = shorts_config.video_template
        self.template_config = self.video_template.template_config

        self.required_assets = EditTemplate.get(
            self.video_template.edit_template.lower()
        ).required_assets

        # Setup all the modules

        self.image_gen = ImageGenerator(
            provider=shorts_config.images_config.provider,
            max_width=self.template_config.max_image_width,
            max_height=self.template_config.max_image_height,
            image_style=self.template_config.image_style,
            api_key=self.image_api_key,
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
            generate_question=AssetType.QUESTION in self.required_assets,
            provider=shorts_config.script_config.provider,
            api_key=self.llm_api_key,
            **shorts_config.script_config.provider_config,
        )

        self.voice_gen = VoiceGenerator(
            avatars=self.avatars,
            tts_f5tts_api_key=self.tts_f5tts_api_key,
            tts_lemonfox_api_key=self.tts_lemonfox_api_key,
        )

        self.lipsync_gen = LipsyncGenerator(
            avatars=self.avatars, lipsync_float_api_key=self.lipsync_float_api_key
        )

        self.subtitle_gen = SubtitleGenerator(
            shorts_config.subtitle_config.provider,
            **shorts_config.subtitle_config.provider_config,
            api_key=self.subtitles_api_key,
        )

        question_provider_config = shorts_config.question_config.provider_config.copy()
        if shorts_config.question_config.provider == "motion_graphic":
            question_provider_config["graphic_class"] = (
                self.template_config.get_question_graphic_class()
            )

        self.question_gen = QuestionGenerator(
            provider=shorts_config.question_config.provider,
            **question_provider_config,
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

    def _save_debug_state(self, reel_series: ReelSeries, stage: str):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"logs/assets_{stage}_{timestamp}.pkl"
            with open(filepath, "wb") as f:
                pickle.dump(reel_series, f)
            self.logger.info(f"Saved checkpoint: {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")

    async def generate_shorts_async(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
    ) -> list[str]:

        # Script
        self.logger.info("Generating scripts...")
        reel_series = None
        if AssetType.SCRIPT in self.required_assets:
            # reel_series = await self.script_gen.generate_script(
            #    num_reels=amount, files=files, user_input=user_input
            # )
            reel_json = Path("tests/test_configs/mock_script_short.json").read_text()
            reel_series = ReelSeries.model_validate_json(reel_json)

            self._save_debug_state(reel_series, "script")

        if not reel_series:
            self.logger.warning("No script generated or loaded. Exiting.")
            return []

        # static faces
        if AssetType.STATICFACE in self.required_assets:
            for reel in reel_series.reels:
                populate_reel_static_faces(reel, self.avatars)

        # TTS, Images, LaTex
        self.logger.info("Generating voiceover, images, latex...")

        async def process_reel_media(reel):
            tasks = []
            if AssetType.VOICE in self.required_assets:
                tasks.append(self.voice_gen.populate_reel(reel))
            if AssetType.IMAGES in self.required_assets:
                tasks.append(self.image_gen.populate_reel(reel))
            if AssetType.LATEX in self.required_assets:
                tasks.append(self.latex_gen.populate_reel(reel))

            if tasks:
                await asyncio.gather(*tasks)
            return reel

        await asyncio.gather(*[process_reel_media(reel) for reel in reel_series.reels])
        self._save_debug_state(reel_series, "media")

        # Lipsync, Subtitles, Questions
        self.logger.info("Generating lipsync video, subtitles, and questions...")

        async def process_reel_secondary(reel):
            tasks = []
            if AssetType.LIPSYNC in self.required_assets:
                tasks.append(self.lipsync_gen.populate_reel(reel))
            if AssetType.SUBTITLES in self.required_assets:
                tasks.append(self.subtitle_gen.populate_reel(reel))
            if AssetType.QUESTION in self.required_assets:
                tasks.append(self.question_gen.populate_reel(reel))

            if tasks:
                await asyncio.gather(*tasks)
            return reel

        await asyncio.gather(
            *[process_reel_secondary(reel) for reel in reel_series.reels]
        )
        self._save_debug_state(reel_series, "secondary_assets")

        # Video Edit
        self.logger.info("Generating final video...")
        results = []

        for reel in reel_series.reels:
            results.append(self.video_gen.compose(reel=reel))

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
