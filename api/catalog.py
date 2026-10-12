"""Shared catalog reads used by both the REST routers and the MCP server."""

from sqlmodel import Session, select

from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from api.models import (
    Avatar,
    GenerationConfig,
    VideoTemplate,
    VideoTemplateRead,
    VideoTemplateTag,
)


def list_avatars(session: Session) -> list[Avatar]:
    """Return all avatars."""
    return list(session.exec(select(Avatar)).all())


def list_video_templates(session: Session) -> list[VideoTemplateRead]:
    """Return all video templates with credit cost and toggleable tags."""
    result = []
    for t in session.exec(select(VideoTemplate)).all():
        assert t.id is not None  # rows read from the DB always have a PK
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
                thumbnail_url=t.thumbnail_url,
                tags=tags,
            )
        )
    return result


def list_generation_configs(session: Session) -> list[GenerationConfig]:
    """Return all generation configs (callers must not leak `data`)."""
    return list(session.exec(select(GenerationConfig)).all())
