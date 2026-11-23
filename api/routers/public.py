from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from api.database import get_session
from api.catalog import (
    list_avatars as _list_avatars,
    list_generation_configs as _list_generation_configs,
    list_video_templates as _list_video_templates,
)
from api.models import (
    Avatar,
    VideoTemplateRead,
    GenerationConfigRead,
    JobStatus,
    PublicVideoRead,
    Reel,
)

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/videos/{share_token}", response_model=PublicVideoRead)
async def get_shared_video(share_token: str, session: Session = Depends(get_session)):
    reel = session.exec(select(Reel).where(Reel.share_token == share_token)).first()
    if not reel or reel.status != JobStatus.DONE or not reel.cloudflare_r2_url:
        raise HTTPException(status_code=404, detail="Video not found")
    return PublicVideoRead.model_validate(reel, from_attributes=True)


@router.get("/avatars", response_model=list[Avatar])
def list_avatars(session: Session = Depends(get_session)):
    """
    Lists all available Avatars.
    """
    return _list_avatars(session)


@router.get("/video-templates", response_model=list[VideoTemplateRead])
def list_templates(session: Session = Depends(get_session)):
    """
    Lists all available Video Templates with their credit cost and togglable tags.
    """
    return _list_video_templates(session)


@router.get("/generation-configs", response_model=list[GenerationConfigRead])
def list_generation_configs(session: Session = Depends(get_session)):
    """
    Lists all available GenerationConfigs.
    """
    return _list_generation_configs(session)
