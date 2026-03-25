from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from api.database import get_session
from api.auth import get_current_admin_user
from api.models import Avatar, VideoTemplate, User, AvatarCreate, VideoTemplateCreate

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


@router.post("/video-templates", response_model=VideoTemplate)
def create_or_update_template(
    template_in: VideoTemplateCreate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Adds or updates a Video Template configuration.
    """
    try:
        VideoTemplate(name=template_in.name, data=template_in.data).to_pydantic()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid template configuration: {str(e)}"
        )

    existing = session.exec(
        select(VideoTemplate).where(VideoTemplate.name == template_in.name)
    ).first()
    if existing:
        existing.data = template_in.data
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_template = VideoTemplate(name=template_in.name, data=template_in.data)
    session.add(new_template)
    session.commit()
    session.refresh(new_template)
    return new_template
