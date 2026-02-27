import asyncio
import logging
import os
import pickle
from datetime import datetime
from enum import IntEnum
from aishorts.modules.script.script_generator import ScriptGenerator
from aishorts.modules.tts.voice_generator import VoiceGenerator
from aishorts.modules.lipsync.lipsync_generator import LipsyncGenerator
from aishorts.modules.video_edit.video_generator import VideoGenerator
from aishorts.modules.subtitles.subtitle_generator import SubtitleGenerator
from aishorts.modules.video_edit.video_edit import VideoTemplate
from aishorts.modules.avatar import Avatar
from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from aishorts.modules.script.script import AssetType
from importlib.resources import read_text
from pydantic import BaseModel, Field
from aishorts.modules.image.image_generator import ImageGenerator
from aishorts.modules.latex.latex_generator import LatexGenerator
from aishorts.modules.manim.manim_generator import ManimGenerator
from aishorts.modules.script.script import ReelSeries, ReelSeriesOutput, ReelOutput
from aishorts.modules.question.question_generator import QuestionGenerator
from aishorts.modules.lipsync.lipsync_providers import populate_reel_static_faces
from pathlib import Path
from aishorts.modules.song.song_generator import SongGenerator
from aishorts.utils.r2_handler import CloudflareR2


class PipelineStage(IntEnum):
    SCRIPT = 0
    PRIMARY = 1
    SECONDARY = 2


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


class ManimConfig(BaseModel):
    base_instructions: str | None = Field(
        default_factory=lambda: read_text(
            "aishorts.resources", "manim_instructions_default.txt"
        )
    )
    provider: str = "local"
    provider_config: dict = Field(default_factory=dict)


class SubtitleConfig(BaseModel):
    provider: str = "elevenlabs"
    provider_config: dict = Field(default_factory=dict)


class QuestionConfig(BaseModel):
    provider: str = "motion_graphic"
    provider_config: dict = Field(default_factory=dict)


class SongConfig(BaseModel):
    provider: str = "minimax"
    provider_config: dict = Field(default_factory=dict)


class ShortsConfig(BaseModel):
    avatars: list[Avatar]
    video_template: VideoTemplate
    script_config: ScriptConfig = Field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = Field(default_factory=SubtitleConfig)
    images_config: ImagesConfig = Field(default_factory=ImagesConfig)
    latex_config: LatexConfig = Field(default_factory=LatexConfig)
    manim_config: ManimConfig = Field(default_factory=ManimConfig)
    question_config: QuestionConfig = Field(default_factory=QuestionConfig)
    song_config: SongConfig = Field(default_factory=SongConfig)


class ShortsGenerator:
    """
    Not required to assign all api keys, just the ones that are used in the generation.
    """

    def __init__(
        self,
        shorts_config: ShortsConfig,
        tts_f5tts_api_key: str | None = None,
        tts_lemonfox_api_key: str | None = None,
        lipsync_float_api_key: str | None = None,
        subtitles_api_key: str | None = None,
        llm_api_key: str | None = None,
        image_api_key: str | None = None,
        ffmpeg_api_key: str | None = None,
        minimax_api_key: str | None = None,
    ):
        # --- API Keys ---
        self.tts_f5tts_api_key = tts_f5tts_api_key
        self.tts_lemonfox_api_key = tts_lemonfox_api_key
        self.lipsync_float_api_key = lipsync_float_api_key
        self.subtitles_api_key = subtitles_api_key
        self.llm_api_key = llm_api_key
        self.image_api_key = image_api_key
        self.ffmpeg_api_key = ffmpeg_api_key
        self.minimax_api_key = minimax_api_key

        self._setup_logging()
        self.update_config(shorts_config)

    def update_config(self, shorts_config: ShortsConfig):
        self.avatars = shorts_config.avatars
        self.video_template = shorts_config.video_template
        self.template_config = self.video_template.template_config

        self.required_assets = EditTemplate.get(
            self.video_template.edit_template.lower()
        ).required_assets

        self.allowed_blocks = EditTemplate.get(
            self.video_template.edit_template.lower()
        ).allowed_blocks

        # --- Setup all the modules ---

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

        self.manim_gen = ManimGenerator(
            provider=shorts_config.manim_config.provider,
            base_instructions=shorts_config.manim_config.base_instructions,
            **shorts_config.manim_config.provider_config,
        )

        self.script_gen = ScriptGenerator(
            base_instructions=shorts_config.script_config.base_instructions,
            avatars=self.avatars,
            generate_latex=AssetType.LATEX in self.required_assets,
            generate_image=AssetType.IMAGES in self.required_assets,
            generate_manim=AssetType.MANIM in self.required_assets,
            generate_question=AssetType.QUESTION in self.required_assets,
            provider=shorts_config.script_config.provider,
            allowed_blocks=self.allowed_blocks,
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

        self.video_gen = VideoGenerator(
            video_template=shorts_config.video_template,
            # api_key=self.ffmpeg_api_key,
        )

        self.song_gen = SongGenerator(
            provider=shorts_config.song_config.provider,
            minimax_api_key=self.minimax_api_key,
            style_prompt=self.template_config.style_prompt,
            **shorts_config.song_config.provider_config,
        )

        # -- Group generators for pipeline execution --

        self.primary_generators = {
            AssetType.VOICE: self.voice_gen,
            AssetType.IMAGES: self.image_gen,
            AssetType.LATEX: self.latex_gen,
            AssetType.MANIM: self.manim_gen,
            AssetType.SONG: self.song_gen,
        }

        self.secondary_generators = {
            AssetType.LIPSYNC: self.lipsync_gen,
            AssetType.SUBTITLES: self.subtitle_gen,
            AssetType.QUESTION: self.question_gen,
        }

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

    def _save_debug_state(self, reel_series: ReelSeries, stage: PipelineStage):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"logs/{stage.name.lower()}_stage_{timestamp}.pkl"
            with open(filepath, "wb") as f:
                pickle.dump(reel_series, f)
            self.logger.info(f"Saved checkpoint: {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")

    def _load_checkpoint(self, path: str) -> tuple[ReelSeries, PipelineStage]:
        """Loads the pickle and determines the stage from the filename."""
        self.logger.info(f"Resuming from checkpoint: {path}")
        with open(path, "rb") as f:
            reel_series = pickle.load(f)

        filename = os.path.basename(path)

        # Assuming format "{stage}_stage_{timestamp}.pkl"
        parts = filename.split("_")
        try:
            stage = PipelineStage[parts[0].upper()]
        except KeyError:
            self.logger.warning(
                f"Unknown stage '{parts[0]}' in filename. Defaulting to SCRIPT."
            )
            stage = PipelineStage.SCRIPT

        return reel_series, stage

    async def _populate_reels(self, reel_series: ReelSeries, generators: dict):
        """Helper to run generators concurrently for all reels."""

        async def process_reel(reel):
            tasks = []
            for asset_type, generator in generators.items():
                if asset_type in self.required_assets:
                    tasks.append(generator.populate_reel(reel))
            if tasks:
                await asyncio.gather(*tasks)

        await asyncio.gather(*[process_reel(reel) for reel in reel_series.reels])

    async def generate_shorts_async(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
        resume_from: str | None = None,
        mock_script: str | None = None,
    ) -> ReelSeriesOutput:

        current_stage = PipelineStage.SCRIPT
        reel_series = None

        # --- 1. Load Checkpoint Logic ---
        if resume_from:
            if not os.path.exists(resume_from):
                raise FileNotFoundError(f"Checkpoint file not found: {resume_from}")

            reel_series, loaded_stage = self._load_checkpoint(resume_from)

            # We start *after* the loaded stage
            current_stage = loaded_stage + 1
            self.logger.info(f"Resuming pipeline AFTER stage: '{loaded_stage.name}'")

        # --- 2. Script Stage ---

        if current_stage <= PipelineStage.SCRIPT:
            self.logger.info("Generating scripts...")
            if AssetType.SCRIPT in self.required_assets:

                if mock_script:
                    reel_json = Path(mock_script).read_text()
                    reel_series = ReelSeries.model_validate_json(reel_json)
                else:
                    reel_series = await self.script_gen.generate_script(
                        num_reels=amount, files=files, user_input=user_input
                    )

                self._save_debug_state(reel_series, PipelineStage.SCRIPT)

        if not reel_series:
            self.logger.warning("No script generated or loaded. Exiting.")
            return ReelSeriesOutput(topic="Error", reels=[])

        # --- 3. Static Faces ---
        # fast enough to run anytime

        if AssetType.STATICFACE in self.required_assets:
            for reel in reel_series.reels:
                populate_reel_static_faces(reel, self.avatars)

        # --- 4. Primary Stage ---

        if current_stage <= PipelineStage.PRIMARY:
            self.logger.info("Generating voiceover, images, latex, manim...")
            await self._populate_reels(reel_series, self.primary_generators)
            self._save_debug_state(reel_series, PipelineStage.PRIMARY)

        # --- 5. Secondary Stage ---

        if current_stage <= PipelineStage.SECONDARY:
            self.logger.info("Generating lipsync video, subtitles, and questions...")
            await self._populate_reels(reel_series, self.secondary_generators)
            self._save_debug_state(reel_series, PipelineStage.SECONDARY)

        # --- 6. Final Video ---

        self.logger.info("Generating final video...")

        # Initialize R2 Handler
        r2 = CloudflareR2()

        reel_outputs = []
        for reel in reel_series.reels:
            # Compose Video
            result = await self.video_gen.compose(reel=reel)
            file_path_str = (
                result.filepath if hasattr(result, "filepath") else str(result)
            )

            # Upload to R2
            filename = os.path.basename(file_path_str)
            key = f"generated/{filename}"
            presigned_url = await asyncio.to_thread(r2.upload_file, file_path_str, key)

            reel_outputs.append(
                ReelOutput(
                    title=reel.title,
                    description=reel.description,
                    local_path=file_path_str,
                    presigned_url=presigned_url,
                )
            )

        return ReelSeriesOutput(topic=reel_series.topic, reels=reel_outputs)

    def generate_shorts(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
        resume_from: str | None = None,
        mock_script: str | None = None,
    ) -> ReelSeriesOutput:
        asyncio.run(
            self.generate_shorts_async(
                amount=amount,
                files=files,
                user_input=user_input,
                resume_from=resume_from,
                mock_script=mock_script,
            ),
        )
