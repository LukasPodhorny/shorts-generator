"""Catalog tools: avatars, video templates, generation configs."""

from api import catalog as catalog_service
from api.mcp.auth import require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors
from api.models import GenerationConfigRead


def list_avatars() -> list[dict]:
    """List all available narrator avatars with their voice and persona config.

    Use the returned names as `avatar_names` when starting a generation.
    """
    with mcp_errors("list_avatars"):
        require_scope("read")
        with session_scope() as session:
            return [a.model_dump() for a in catalog_service.list_avatars(session)]


def list_video_templates() -> list[dict]:
    """List all available video templates with credit cost and toggleable tags.

    Each template reports `credits` (cost per reel), preview/thumbnail URLs,
    and `tags`: asset types the caller may enable via `enabled_tags`, each
    with its default on/off state. Use the template `name` when generating.
    """
    with mcp_errors("list_video_templates"):
        require_scope("read")
        with session_scope() as session:
            return [
                t.model_dump()
                for t in catalog_service.list_video_templates(session)
            ]


def list_generation_configs() -> list[dict]:
    """List all generation configs (names only).

    A config selects the providers/models for each pipeline stage. Pass its
    `name` as `config_name` when generating, or omit it to use the default
    (the entry with `is_default: true`).
    """
    with mcp_errors("list_generation_configs"):
        require_scope("read")
        with session_scope() as session:
            return [
                GenerationConfigRead.model_validate(
                    c, from_attributes=True
                ).model_dump()
                for c in catalog_service.list_generation_configs(session)
            ]
