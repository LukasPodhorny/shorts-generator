from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from api.database import get_session
from api.models import Avatar, VideoTemplate, VideoTemplateRead, GenerationConfig, GenerationConfigRead

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/avatars", response_model=list[Avatar])
def list_avatars(session: Session = Depends(get_session)):
    """
    Lists all available Avatars.
    """
    return session.exec(select(Avatar)).all()


@router.get("/video-templates", response_model=list[VideoTemplateRead])
def list_templates(session: Session = Depends(get_session)):
    """
    Lists all available Video Templates with their credit cost.
    """
    return session.exec(select(VideoTemplate)).all()


@router.get("/generation-configs", response_model=list[GenerationConfigRead])
def list_generation_configs(session: Session = Depends(get_session)):
    """
    Lists all available GenerationConfigs.
    """
    return session.exec(select(GenerationConfig)).all()
