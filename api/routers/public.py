from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from api.database import get_session
from api.models import (
    Avatar,
    VideoTemplate,
    VideoTemplateRead,
    VideoTemplateTag,
    GenerationConfig,
    GenerationConfigRead,
)
from aishorts.modules.video_edit.video_edit_templates import EditTemplate

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
    Lists all available Video Templates with their credit cost and togglable tags.
    """
    db_templates = session.exec(select(VideoTemplate)).all()
    result = []
    for t in db_templates:
        tags: list[VideoTemplateTag] = []
        edit_template_name = (t.data or {}).get("edit_template", "")
        if edit_template_name:
            try:
                template_cls = EditTemplate.get(edit_template_name.lower())
                tags = [
                    VideoTemplateTag(asset_type=a.value, default=default)
                    for a, default in template_cls.tag_assets.items()
                ]
            except ValueError:
                tags = []

        result.append(
            VideoTemplateRead(
                id=t.id,
                name=t.name,
                credits=t.credits,
                preview_url=t.preview_url,
                tags=tags,
            )
        )
    return result


@router.get("/generation-configs", response_model=list[GenerationConfigRead])
def list_generation_configs(session: Session = Depends(get_session)):
    """
    Lists all available GenerationConfigs.
    """
    return session.exec(select(GenerationConfig)).all()
