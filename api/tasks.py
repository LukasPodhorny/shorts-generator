import os
import logging
from sqlmodel import Session, select
from fastapi.concurrency import run_in_threadpool
from api.database import engine
from api.models import ReelSeries, Reel, Avatar, VideoTemplate, GenerationConfig, JobStatus, User

# Import core library
from aishorts import ShortsGenerator, ShortsConfig
from aishorts.shorts_generator import PipelineStage
from typing import Optional


logger = logging.getLogger(__name__)


def _update_series_status(series_id: int, stage: PipelineStage, reel_series=None):
    """Sync helper to update database based on pipeline stage."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return

        # Map pipeline stages to human-readable strings for the frontend
        status_map = {
            PipelineStage.SCRIPT: "Generating script...",
            PipelineStage.PRIMARY: "Generating assets (audio, images)...",
            PipelineStage.SECONDARY: "Finalizing assets (lipsync, subtitles)...",
        }
        
        # Update topic as soon as it's available (after SCRIPT stage)
        if reel_series and reel_series.topic:
            series.topic = reel_series.topic

        # Update series thumbnail URL if available
        if reel_series and hasattr(reel_series, 'thumbnail_url') and reel_series.thumbnail_url:
            series.thumbnail_url = reel_series.thumbnail_url

        # Update reel titles, descriptions, and thumbnails after SCRIPT stage
        if reel_series and reel_series.reels:
            db_reels = session.exec(
                select(Reel).where(Reel.series_id == series_id).order_by(Reel.sequence_number)
            ).all()

            for i, generated_reel in enumerate(reel_series.reels):
                if i < len(db_reels):
                    db_reel = db_reels[i]
                    if generated_reel.title:
                        db_reel.title = generated_reel.title
                    if generated_reel.description:
                        db_reel.description = generated_reel.description
                    # Update thumbnail URL if available
                    if hasattr(generated_reel, 'thumbnail_url') and generated_reel.thumbnail_url:
                        db_reel.thumbnail_url = generated_reel.thumbnail_url
                    session.add(db_reel)
            
        session.add(series)
        session.commit()


def _prepare_generation_config(
    series_id: int, request_data: dict
) -> Optional[ShortsConfig]:
    """Sync helper to fetch data and update status."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return None

        # Mark series and reels as processing
        series.status = JobStatus.PROCESSING
        session.add(series)

        reels = session.exec(select(Reel).where(Reel.series_id == series_id)).all()
        for reel in reels:
            reel.status = JobStatus.PROCESSING
            session.add(reel)

        session.commit()

        # 1. Load Configuration from DB
        # Fetch Avatars
        selected_avatars = []
        for name in request_data.get("avatar_names", []):
            statement = select(Avatar).where(Avatar.name == name)
            db_avatar = session.exec(statement).first()
            if db_avatar:
                selected_avatars.append(db_avatar.to_pydantic())

        if not selected_avatars:
            raise ValueError("No valid avatars found for request")

        # Fetch Template
        template_name = request_data.get("template_name")
        statement = select(VideoTemplate).where(VideoTemplate.name == template_name)
        db_template = session.exec(statement).first()

        if not db_template:
            raise ValueError(f"Template '{template_name}' not found")

        video_template = db_template.to_pydantic()

        # Fetch GenerationConfig (by name, or fall back to default)
        config_name = request_data.get("config_name")
        if config_name:
            gen_config = session.exec(
                select(GenerationConfig).where(GenerationConfig.name == config_name)
            ).first()
            if not gen_config:
                raise ValueError(f"GenerationConfig '{config_name}' not found")
        else:
            gen_config = session.exec(
                select(GenerationConfig).where(GenerationConfig.is_default == True)
            ).first()

        config_kwargs = gen_config.to_config_kwargs() if gen_config else {}

        return ShortsConfig(
            avatars=selected_avatars,
            video_template=video_template,
            enabled_tags=request_data.get("enabled_tags"),
            **config_kwargs,
        )


def _save_generation_results(series_id: int, output):
    """Sync helper to save results to DB."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return

        # Update Series Topic and Thumbnail
        series.topic = output.topic
        series.thumbnail_url = output.thumbnail_url
        session.add(series)

        # 4. Upload and Update Reels
        reels = session.exec(select(Reel).where(Reel.series_id == series_id).order_by(Reel.sequence_number)).all()

        for i, reel_out in enumerate(output.reels):
            if i < len(reels):
                reel = reels[i]

                reel.title = reel_out.title
                reel.description = reel_out.description
                reel.local_path = reel_out.local_path
                reel.cloudflare_r2_url = reel_out.presigned_url
                reel.thumbnail_url = reel_out.thumbnail_url
                reel.duration = reel_out.duration
                reel.status = JobStatus.DONE
                session.add(reel)

        series.status = JobStatus.DONE
        session.add(series)
        session.commit()


def _mark_series_failed(series_id: int, refund_amount: int = 0):
    """Sync helper to mark series and all its reels as failed, refunding credits."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return

        # Idempotency: only refund if not already marked FAILED
        already_failed = series.status == JobStatus.FAILED

        series.status = JobStatus.FAILED
        session.add(series)

        # Mark all reels as failed too
        reels = session.exec(select(Reel).where(Reel.series_id == series_id)).all()
        for reel in reels:
            reel.status = JobStatus.FAILED
            session.add(reel)

        if refund_amount > 0 and not already_failed:
            user = session.get(User, series.user_id)
            if user:
                user.credits += refund_amount
                session.add(user)
                logger.info(
                    f"Refunded {refund_amount} credits to user {user.id} for failed series {series_id}"
                )

        session.commit()


async def process_reel_task(series_id: int, request_data: dict, total_cost: int = 0):
    """
    Background task to generate shorts and update DB.
    """
    try:
        # 1. Prepare Config
        shorts_config = await run_in_threadpool(
            _prepare_generation_config, series_id, request_data
        )

        if not shorts_config:
            logger.error(f"Series {series_id} not found or config failed.")
            return

        # 2. Initialize Generator
        shorts_generator = ShortsGenerator(
            shorts_config=shorts_config,
        )

        # 3. Define the status callback for the generator
        async def status_callback(stage, reel_series):
            await run_in_threadpool(_update_series_status, series_id, stage, reel_series)

        # 4. Generate (Async)
        output = await shorts_generator.generate_shorts_async(
            amount=request_data.get("amount", 1),
            files=request_data.get("files"),
            user_input=request_data.get("input_text"),
            status_callback=status_callback,
        )

        # 5. Save Results
        await run_in_threadpool(_save_generation_results, series_id, output)

    except Exception as e:
        logger.exception(f"Job Failed for series {series_id}: {e}")
        await run_in_threadpool(_mark_series_failed, series_id, total_cost)
