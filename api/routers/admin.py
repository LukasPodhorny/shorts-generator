import json
import os
import shutil
import subprocess
import tempfile
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from api.database import get_session
from api.auth import get_current_admin_user
from api.models import (
    Avatar, VideoTemplate, User, AvatarCreate, VideoTemplateCreate,
    GenerationConfig, GenerationConfigCreate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/avatars", response_model=Avatar)
def create_or_update_avatar(
    avatar_in: AvatarCreate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Adds or updates an Avatar configuration.
    """
    try:
        # Validate that the data matches the core library structure
        # We create a temporary DB model to use the helper method
        Avatar(name=avatar_in.name, data=avatar_in.data).to_pydantic()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid avatar configuration: {str(e)}"
        )

    existing = session.exec(select(Avatar).where(Avatar.name == avatar_in.name)).first()
    if existing:
        existing.data = avatar_in.data
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_avatar = Avatar(name=avatar_in.name, data=avatar_in.data)
    session.add(new_avatar)
    session.commit()
    session.refresh(new_avatar)
    return new_avatar


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _public_url(key: str) -> str:
    domain = os.getenv("R2_PUBLIC_DOMAIN")
    if domain:
        return f"https://{domain}/{key}"
    # Fallback: presigned URL via boto3
    return _r2_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": os.getenv("R2_BUCKET"), "Key": key},
        ExpiresIn=604800,
    )


def _extract_thumbnail(video_path: str, thumb_path: str) -> None:
    # Grab a frame at 1s; first frames are often black/fade-in.
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "3",
            thumb_path,
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not os.path.exists(thumb_path):
        raise RuntimeError(
            f"ffmpeg failed to extract thumbnail: {result.stderr.decode(errors='ignore')[-500:]}"
        )


async def _upload_preview_and_thumbnail(name: str, preview: UploadFile) -> tuple[str, str]:
    """Saves upload to tmp, extracts thumbnail, uploads both to R2, returns (preview_url, thumbnail_url)."""
    bucket = os.getenv("R2_BUCKET")
    if not bucket:
        raise HTTPException(status_code=500, detail="R2_BUCKET is not configured")

    tmp_dir = tempfile.mkdtemp(prefix="tpl_preview_")
    try:
        video_path = os.path.join(tmp_dir, f"{name}.mp4")
        thumb_path = os.path.join(tmp_dir, f"{name}.jpg")

        with open(video_path, "wb") as f:
            while chunk := await preview.read(1024 * 1024):
                f.write(chunk)

        await run_in_threadpool(_extract_thumbnail, video_path, thumb_path)

        video_key = f"assets/preview/{name}.mp4"
        thumb_key = f"assets/thumbnail/{name}.jpg"

        s3 = _r2_client()
        await run_in_threadpool(
            s3.upload_file, video_path, bucket, video_key,
            {"ContentType": "video/mp4"},
        )
        await run_in_threadpool(
            s3.upload_file, thumb_path, bucket, thumb_key,
            {"ContentType": "image/jpeg"},
        )

        return _public_url(video_key), _public_url(thumb_key)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/video-templates", response_model=VideoTemplate)
async def create_or_update_template(
    name: str = Form(...),
    data: str = Form(...),
    preview: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Adds or updates a Video Template. Accepts multipart/form-data:
      - name: template name
      - data: JSON-encoded template config
      - preview (optional): .mp4 preview video. When provided, it is uploaded to R2
        and a thumbnail (frame at 1s) is generated and uploaded alongside it.
    """
    try:
        data_dict = json.loads(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"`data` is not valid JSON: {e}")

    try:
        VideoTemplate(name=name, data=data_dict).to_pydantic()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid template configuration: {str(e)}"
        )

    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    if preview is not None and preview.filename:
        preview_url, thumbnail_url = await _upload_preview_and_thumbnail(name, preview)

    existing = session.exec(
        select(VideoTemplate).where(VideoTemplate.name == name)
    ).first()
    if existing:
        existing.data = data_dict
        if preview_url:
            existing.preview_url = preview_url
            existing.thumbnail_url = thumbnail_url
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_template = VideoTemplate(
        name=name,
        data=data_dict,
        preview_url=preview_url,
        thumbnail_url=thumbnail_url,
    )
    session.add(new_template)
    session.commit()
    session.refresh(new_template)
    return new_template


@router.post("/generation-configs", response_model=GenerationConfig)
def create_or_update_generation_config(
    config_in: GenerationConfigCreate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Adds or updates a GenerationConfig (provider/model settings for the pipeline).
    """
    # Validate by trying to build the config kwargs
    try:
        GenerationConfig(name=config_in.name, data=config_in.data).to_config_kwargs()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid generation config: {str(e)}"
        )

    # If marking as default, unset any existing default
    if config_in.is_default:
        old_default = session.exec(
            select(GenerationConfig).where(GenerationConfig.is_default == True)
        ).first()
        if old_default:
            old_default.is_default = False
            session.add(old_default)

    existing = session.exec(
        select(GenerationConfig).where(GenerationConfig.name == config_in.name)
    ).first()
    if existing:
        existing.data = config_in.data
        existing.is_default = config_in.is_default
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_config = GenerationConfig(
        name=config_in.name, data=config_in.data, is_default=config_in.is_default
    )
    session.add(new_config)
    session.commit()
    session.refresh(new_config)
    return new_config
