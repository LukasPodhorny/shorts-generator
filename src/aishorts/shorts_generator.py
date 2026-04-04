import asyncio
import logging
import os
import pickle
import uuid
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
from typing import Callable, Awaitable, Any


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
    provider: str | None = "gemini"
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
    provider: str = "modal_manim"
    provider_config: dict = Field(default_factory=dict)


class SubtitleConfig(BaseModel):
    provider: str = "modal_wav2vec_aligner"
    provider_config: dict = Field(default_factory=dict)


class QuestionConfig(BaseModel):
    provider: str = "motion_graphic"
    provider_config: dict = Field(default_factory=dict)


class SongConfig(BaseModel):
    provider: str = "minimax"
    provider_config: dict = Field(default_factory=dict)


class FFmpegConfig(BaseModel):
    provider: str = "modal_ffmpeg"
    compression_profile: str = "very_small"
    quality_value: int | None = None
    max_video_bitrate: str | None = "2M"
    audio_bitrate: str = "96k"
    encoder_preset: str | None = None
    provider_config: dict = Field(default_factory=dict)


class ShortsConfig(BaseModel):
    avatars: list[Avatar]
    video_template: VideoTemplate
    script_config: ScriptConfig = Field(default_factory=ScriptConfig)
    subtitle_config: SubtitleConfig = Field(default_factory=SubtitleConfig)
    ffmpeg_config: FFmpegConfig = Field(default_factory=FFmpegConfig)
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
            provider=shorts_config.ffmpeg_config.provider,
            download_results=False,
            compression_profile=shorts_config.ffmpeg_config.compression_profile,
            quality_value=shorts_config.ffmpeg_config.quality_value,
            max_video_bitrate=shorts_config.ffmpeg_config.max_video_bitrate,
            audio_bitrate=shorts_config.ffmpeg_config.audio_bitrate,
            encoder_preset=shorts_config.ffmpeg_config.encoder_preset,
            api_key=self.ffmpeg_api_key,
            **shorts_config.ffmpeg_config.provider_config,
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

        # Ensure all related models are rebuilt before validation to handle Union types properly
        from aishorts.modules.script.script import (
            ReelSeries,
            Reel,
            DialogueBlock,
            QuestionBlock,
            SongBlock,
        )

        for model in [DialogueBlock, QuestionBlock, SongBlock, Reel, ReelSeries]:
            try:
                model.model_rebuild()
            except:
                pass

        with open(path, "rb") as f:
            obj = pickle.load(f)

            # Use a safer way to get the dictionary data without triggering full serialization
            # which might fail if the unpickled object's internal Pydantic state is corrupted.
            if isinstance(obj, ReelSeries):
                # If it's already a ReelSeries, we still want to re-validate it
                # to ensure all fields from the NEW schema are present.
                try:
                    data = obj.model_dump()
                except (TypeError, AttributeError):
                    # Fallback if model_dump fails due to MockValSer or similar
                    import json

                    try:
                        # try legacy dict() if available
                        data = obj.dict() if hasattr(obj, "dict") else obj.__dict__
                    except:
                        data = obj
            elif hasattr(obj, "__dict__"):
                data = obj.__dict__
            else:
                data = obj

            # Final attempt: if it's a dict or we extracted one, validate it
            try:
                reel_series = ReelSeries.model_validate(data)
            except Exception as e:
                self.logger.error(f"Failed to validate checkpoint data: {e}")
                # If validation fails, try to return the object as is if it looks like a ReelSeries
                if hasattr(obj, "reels") and hasattr(obj, "topic"):
                    reel_series = obj
                else:
                    raise e

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
        keep_assets: bool = False,
        status_callback: Callable[[PipelineStage, ReelSeries | None], Awaitable[None]]
        | None = None,
    ) -> ReelSeriesOutput:

        current_stage = PipelineStage.SCRIPT
        reel_series = None

        # Generate a unique session ID for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"run_{timestamp}_{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Starting generation session: {session_id}")

        reel_outputs = []
        intermediate_keys = []

        try:
            # --- 1. Load Checkpoint Logic ---
            if resume_from:
                if not os.path.exists(resume_from):
                    raise FileNotFoundError(f"Checkpoint file not found: {resume_from}")

                reel_series, loaded_stage = self._load_checkpoint(resume_from)

                # Re-download assets that were previously generated but are missing locally
                # (essential for ephemeral environments like Railway).
                self.logger.info(
                    "Ensuring all generated assets are available locally..."
                )
                await asyncio.gather(
                    *[
                        self.video_gen.ensure_assets_local(reel)
                        for reel in reel_series.reels
                    ]
                )

                # We start *after* the loaded stage
                current_stage = loaded_stage + 1
                self.logger.info(
                    f"Resuming pipeline AFTER stage: '{loaded_stage.name}'"
                )

                # Warning for Railway/ephemeral environments
                if current_stage > PipelineStage.SCRIPT and not os.path.exists(
                    "output"
                ):
                    self.logger.warning(
                        "Output directory not found. If you are on an ephemeral environment (like Railway), "
                        "some assets may be missing. The video generator will attempt to re-download "
                        "available assets from URLs."
                    )

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

                    self.logger.info(
                        "Generated script JSON:\n%s",
                        reel_series.model_dump_json(indent=2),
                    )
                    self._save_debug_state(reel_series, PipelineStage.SCRIPT)
                    if status_callback:
                        await status_callback(PipelineStage.SCRIPT, reel_series)

            if not reel_series:
                self.logger.warning("No script generated or loaded. Exiting.")
                return ReelSeriesOutput(topic="Error", reels=[])

            # --- 2.5. Thumbnail Generation ---
            # Generate thumbnails after script is available

            series_thumbnail_url = None
            reel_thumbnails = {}  # Map reel index to thumbnail URL

            if AssetType.IMAGES in self.required_assets:
                self.logger.info("Generating thumbnails...")
                r2 = CloudflareR2()

                # Generate series thumbnail from thumbnail_prompt (fallback to topic)
                thumbnail_source = reel_series.thumbnail_prompt or reel_series.topic
                if thumbnail_source:
                    try:
                        series_thumb_path = os.path.join(
                            self.image_gen.image_gen.OUTPUT_DIR,
                            f"series_thumb_{uuid.uuid4().hex}.png"
                        )
                        await self.image_gen.generate_thumbnail(
                            prompt=thumbnail_source,
                            output_path=series_thumb_path,
                        )
                        series_thumb_key = f"generated/thumbnails/{uuid.uuid4().hex}.png"
                        series_thumbnail_url = await asyncio.to_thread(
                            r2.upload_file, series_thumb_path, series_thumb_key
                        )
                        self.logger.info(f"Series thumbnail uploaded: {series_thumbnail_url}")
                        # Clean up local file
                        if os.path.exists(series_thumb_path):
                            os.remove(series_thumb_path)
                    except Exception as e:
                        self.logger.warning(f"Failed to generate series thumbnail: {e}")

                # Generate thumbnails for each reel from thumbnail_prompt (fallback to description)
                for i, reel in enumerate(reel_series.reels):
                    reel_thumb_source = reel.thumbnail_prompt or reel.description
                    if reel_thumb_source:
                        try:
                            reel_thumb_path = os.path.join(
                                self.image_gen.image_gen.OUTPUT_DIR,
                                f"reel_thumb_{uuid.uuid4().hex}.png"
                            )
                            await self.image_gen.generate_thumbnail(
                                prompt=reel_thumb_source,
                                output_path=reel_thumb_path,
                            )
                            reel_thumb_key = f"generated/thumbnails/{uuid.uuid4().hex}.png"
                            reel_thumbnails[i] = await asyncio.to_thread(
                                r2.upload_file, reel_thumb_path, reel_thumb_key
                            )
                            self.logger.info(f"Reel {i} thumbnail uploaded")
                            # Clean up local file
                            if os.path.exists(reel_thumb_path):
                                os.remove(reel_thumb_path)
                        except Exception as e:
                            self.logger.warning(f"Failed to generate thumbnail for reel {i}: {e}")

            # Store thumbnail URLs in reel_series for callback
            reel_series.thumbnail_url = series_thumbnail_url
            for i, reel in enumerate(reel_series.reels):
                if i in reel_thumbnails:
                    reel.thumbnail_url = reel_thumbnails[i]

            # Call callback to update database with thumbnails
            if status_callback:
                await status_callback(PipelineStage.SCRIPT, reel_series)

            # --- 3. Static Faces ---
            # fast enough to run anytime

            if AssetType.STATICFACE in self.required_assets:
                for i, reel in enumerate(reel_series.reels):
                    populate_reel_static_faces(reel, self.avatars)

            # --- 4. Primary Stage ---

            if current_stage <= PipelineStage.PRIMARY:
                self.logger.info("Generating voiceover, images, latex, manim...")
                await self._populate_reels(reel_series, self.primary_generators)
                self._save_debug_state(reel_series, PipelineStage.PRIMARY)
                if status_callback:
                    await status_callback(PipelineStage.PRIMARY, reel_series)

            # --- 5. Secondary Stage ---

            if current_stage <= PipelineStage.SECONDARY:
                self.logger.info(
                    "Generating lipsync video, subtitles, and questions..."
                )
                await self._populate_reels(reel_series, self.secondary_generators)
                self._save_debug_state(reel_series, PipelineStage.SECONDARY)
                if status_callback:
                    await status_callback(PipelineStage.SECONDARY, reel_series)

            # --- 6. Final Video ---

            self.logger.info("Generating final video...")

            # Initialize R2 Handler
            r2 = CloudflareR2()

            for i, reel in enumerate(reel_series.reels):
                filename = f"{uuid.uuid4().hex}.mp4"
                dest_key = f"generated/{filename}"

                # Compose video directly to the final R2 destination key.
                result = await self.video_gen.compose(
                    reel=reel,
                    session_id=session_id,
                    output_key=dest_key,
                )

                if result.key:
                    presigned_url = result.download_url
                else:
                    self.logger.info(f"Uploading final video to R2: {dest_key}")
                    presigned_url = await asyncio.to_thread(
                        r2.upload_file, result.filepath, dest_key
                    )

                reel_outputs.append(
                    ReelOutput(
                        title=reel.title,
                        description=reel.description,
                        local_path=result.filepath or "",
                        presigned_url=presigned_url,
                        thumbnail_url=reel_thumbnails.get(i),
					duration=getattr(result, "duration", None),
                    )
                )

            return ReelSeriesOutput(
                topic=reel_series.topic,
                thumbnail_url=series_thumbnail_url,
                reels=reel_outputs
            )

        finally:
            # --- 7. Cleanup ---
            await self._cleanup_assets(
                reel_series=reel_series,
                reel_outputs=reel_outputs,
                intermediate_keys=intermediate_keys,
                session_id=session_id,
                keep_assets=keep_assets,
            )

    async def _cleanup_assets(
        self,
        reel_series: ReelSeries | None,
        reel_outputs: list[ReelOutput],
        intermediate_keys: list[str],
        session_id: str,
        keep_assets: bool = False,
    ):
        if keep_assets:
            self.logger.info("Keep assets flag set. Skipping cleanup.")
            return

        self.logger.info("Cleaning up intermediate assets...")
        r2 = CloudflareR2()

        local_to_delete = set()
        r2_to_delete = set(intermediate_keys)

        # 1. Collect from reel_series blocks
        if reel_series:
            for i, reel in enumerate(reel_series.reels):
                for block in reel.blocks:
                    assets = block.assets
                    if not assets:
                        continue

                    # Collect local files (only if they are in the 'output' directory)
                    for path in [
                        getattr(assets, "voice_filepath", None),
                        getattr(assets, "lipsync_filepath", None),
                        getattr(assets, "staticface_filepath", None),
                        getattr(assets, "question_filepath", None),
                        getattr(assets, "song_filepath", None),
                    ]:
                        if path and os.path.exists(path) and "output" in path:
                            local_to_delete.add(path)

                    # Collect R2 keys (staticface_url excluded - permanent assets in shorts-generator/assets/)
                    urls_to_check = [
                        getattr(assets, "voice_url", None),
                        getattr(assets, "lipsync_url", None),
                        # staticface_url intentionally excluded - permanent assets
                        getattr(assets, "song_url", None),
                        getattr(assets, "question_url", None),
                    ]

                    for url in urls_to_check:
                        if url:
                            # Extract string if it's a dict
                            url_str = url.get("url") if isinstance(url, dict) else url
                            if url_str and str(url_str).startswith("http"):
                                try:
                                    key = CloudflareR2.get_key_from_url(url, r2.bucket)
                                    if key and not key.startswith("generated/"):
                                        r2_to_delete.add(key)
                                except:
                                    pass

                    # Media Map (Images, LaTeX, Manim)
                    for media_id, path in assets.media_map.items():
                        if path and os.path.exists(path) and "output" in path:
                            local_to_delete.add(path)
                        url = assets.media_url_map.get(media_id)
                        if url:
                            url_str = url.get("url") if isinstance(url, dict) else url
                            if url_str and str(url_str).startswith("http"):
                                try:
                                    key = CloudflareR2.get_key_from_url(url, r2.bucket)
                                    if key and not key.startswith("generated/"):
                                        r2_to_delete.add(key)
                                except:
                                    pass

        # 2. Collect any local final outputs for deletion (avoid persisting local final files).
        for ro in reel_outputs:
            if ro.local_path and os.path.exists(ro.local_path):
                local_to_delete.add(ro.local_path)

        # Protect final R2 outputs only.
        final_r2_keys = {
            CloudflareR2.get_key_from_url(ro.presigned_url, r2.bucket)
            for ro in reel_outputs
        }

        r2_to_delete -= final_r2_keys

        # 3. Delete local files
        for path in local_to_delete:
            try:
                os.remove(path)
                # self.logger.debug(f"Deleted local file: {path}")
            except Exception as e:
                self.logger.warning(f"Failed to delete local file {path}: {e}")

        # 4. Delete R2 objects
        for key in r2_to_delete:
            try:
                await asyncio.to_thread(r2.delete_file, key)
                # self.logger.debug(f"Deleted R2 object: {key}")
            except Exception as e:
                self.logger.warning(f"Failed to delete R2 key {key}: {e}")

        # 5. Finally, clean up the session uploads prefix (for on-the-fly uploads from providers)
        try:
            uploads_prefix = f"uploads/{session_id}/"
            await asyncio.to_thread(r2.delete_prefix, uploads_prefix)
        except Exception as e:
            self.logger.warning(f"Failed to clean up uploads prefix: {e}")

        # 6. Clean up shared audio uploads from subtitle aligner (uploads/audio/)
        try:
            await asyncio.to_thread(r2.delete_prefix, "uploads/audio/")
        except Exception as e:
            self.logger.warning(f"Failed to clean up uploads/audio prefix: {e}")

    def generate_shorts(
        self,
        amount: int = 1,
        files: list[str] | None = None,
        user_input: str | None = None,
        resume_from: str | None = None,
        mock_script: str | None = None,
        keep_assets: bool = False,
    ) -> ReelSeriesOutput:
        return asyncio.run(
            self.generate_shorts_async(
                amount=amount,
                files=files,
                user_input=user_input,
                resume_from=resume_from,
                mock_script=mock_script,
                keep_assets=keep_assets,
            ),
        )
