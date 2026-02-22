import os
from sqlmodel import Session, select
from api.database import engine
from api.models import ReelSeries, Reel, Avatar, VideoTemplate

# Import core library
from aishorts import ShortsGenerator, ShortsConfig, SubtitleConfig
from aishorts.shorts_generator import ScriptConfig


async def process_reel_task(series_id: int, request_data: dict):
    """
    Background task to generate shorts and update DB.
    """
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series:
            return

        try:
            series.status = "Processing"
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

            # 2. Initialize Generator
            shorts_config = ShortsConfig(
                avatars=selected_avatars,
                video_template=video_template,
                subtitle_config=SubtitleConfig(provider="elevenlabs"),
                script_config=ScriptConfig(provider="gemini"),
            )

            shorts_generator = ShortsGenerator(
                shorts_config=shorts_config,
                llm_api_key=os.getenv("LLM_API_KEY"),
                tts_f5tts_api_key=os.getenv("TTS_API_KEY"),
                subtitles_api_key=os.getenv("SUBTITLES_API_KEY"),
                image_api_key=os.getenv("IMAGE_API_KEY"),
                # Add other keys as needed
            )

            # 3. Generate
            output = await shorts_generator.generate_shorts_async(
                amount=request_data.get("amount", 1),
                files=request_data.get("files"),
                user_input=request_data.get("input_text"),
            )

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
                    reel.status = "Done"
                    session.add(reel)

            series.status = "Done"
            session.add(series)
            session.commit()

        except Exception as e:
            print(f"Job Failed: {e}")
            session.rollback()
            series = session.get(ReelSeries, series_id)
            if series:
                series.status = "Failed"
                session.add(series)
                session.commit()
