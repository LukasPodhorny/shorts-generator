import os
import logging
from sqlmodel import Session, select
from fastapi.concurrency import run_in_threadpool
from api.database import engine
from api.models import ReelSeries, Reel, Avatar, VideoTemplate, JobStatus

# Import core library
from aishorts import ShortsGenerator, ShortsConfig, SubtitleConfig
from aishorts.shorts_generator import ScriptConfig
from typing import Optional


logger = logging.getLogger(__name__)


def _prepare_generation_config(
    series_id: int, request_data: dict
) -> Optional[ShortsConfig]:
    """Sync helper to fetch data and update status."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return None

        series.status = JobStatus.PROCESSING
        session.add(series)
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

        return ShortsConfig(
            avatars=selected_avatars,
            video_template=video_template,
            subtitle_config=SubtitleConfig(provider="elevenlabs"),
            script_config=ScriptConfig(provider="gemini"),
        )


def _save_generation_results(series_id: int, output):
    """Sync helper to save results to DB."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return

        # Update Series Topic
        series.topic = output.topic
        session.add(series)

        # 4. Upload and Update Reels
        reels = session.exec(select(Reel).where(Reel.series_id == series_id)).all()

        for i, reel_out in enumerate(output.reels):
            if i < len(reels):
                reel = reels[i]

                reel.title = reel_out.title
                reel.description = reel_out.description
                reel.local_path = reel_out.local_path
                reel.cloudflare_r2_url = reel_out.presigned_url
                reel.status = JobStatus.DONE
                session.add(reel)

        series.status = JobStatus.DONE
        session.add(series)
        session.commit()


def _mark_series_failed(series_id: int):
    """Sync helper to mark series as failed."""
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if series:
            series.status = JobStatus.FAILED
            session.add(series)
            session.commit()


async def process_reel_task(series_id: int, request_data: dict):
    """
    Background task to generate shorts and update DB.
    Uses run_in_threadpool to avoid blocking the async event loop with sync DB calls.
    """
    try:
        # 1. Prepare Config (Sync DB call)
        shorts_config = await run_in_threadpool(
            _prepare_generation_config, series_id, request_data
        )

        if not shorts_config:
            logger.error(f"Series {series_id} not found or config failed.")
            return

        # 2. Initialize Generator
        shorts_generator = ShortsGenerator(
            shorts_config=shorts_config,
            llm_api_key=os.getenv("LLM_API_KEY"),
            tts_f5tts_api_key=os.getenv("TTS_API_KEY"),
            subtitles_api_key=os.getenv("SUBTITLES_API_KEY"),
            image_api_key=os.getenv("IMAGE_API_KEY"),
        )

        # 3. Generate (Async)
        output = await shorts_generator.generate_shorts_async(
            amount=request_data.get("amount", 1),
            files=request_data.get("files"),
            user_input=request_data.get("input_text"),
        )

        # 4. Save Results (Sync DB call)
        await run_in_threadpool(_save_generation_results, series_id, output)

    except Exception as e:
        logger.exception(f"Job Failed for series {series_id}: {e}")
        await run_in_threadpool(_mark_series_failed, series_id)
