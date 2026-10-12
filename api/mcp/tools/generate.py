"""Generation tools: start reel jobs explicitly or from natural language."""

from api.dispatch import resolve_dispatch
from api.mcp.auth import current_user_token, require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors
from api.models import (
    AttachedFile,
    AttachedLink,
    GenerateRequest,
    PlanRequest,
)
from api.plan_service import plan_to_request
from api.routers.generate import create_generation


async def generate_reels(
    template_name: str,
    avatar_names: list[str],
    amount: int = 1,
    input_text: str | None = None,
    files: list[str] | None = None,
    links: list[str] | None = None,
    config_name: str | None = None,
    enabled_tags: list[str] | None = None,
) -> dict:
    """Start a reel generation job with explicit settings. Costs credits.

    Args:
        template_name: Video template name from list_video_templates.
        avatar_names: 1-4 avatar names from list_avatars.
        amount: How many reels to generate (1-7). Total cost is
            amount x the template's per-reel credit cost.
        input_text: Freeform topic or script direction used as source material.
        files: Uploaded-file keys from list_my_uploads to use as sources.
        links: Public http(s) URLs (articles, YouTube, Wikipedia) as sources.
        config_name: Generation config from list_generation_configs, or omit
            for the default.
        enabled_tags: Asset tags to enable on the template, or omit for the
            template's defaults.

    Returns immediately with `series_id` and `remaining_credits`; the videos
    render in the background. Poll get_series_status until Done or Failed.
    At least one source (input_text, files, or links) is normally needed.
    """
    with mcp_errors("generate_reels"):
        require_scope("write")
        token = current_user_token()
        request = GenerateRequest(
            template_name=template_name,
            avatar_names=avatar_names,
            amount=amount,
            input_text=input_text,
            files=files,
            links=links,
            config_name=config_name,
            enabled_tags=enabled_tags,
        )
        with session_scope() as session:
            response = create_generation(
                request=request,
                user_token=token,
                session=session,
                dispatch_task=resolve_dispatch(),
            )
        return response.model_dump()


async def plan_reels(
    instruction: str,
    attachments: list[AttachedFile | AttachedLink] | None = None,
    template_name: str | None = None,
    avatar_names: list[str] | None = None,
    amount: int | None = None,
    enabled_tags: list[str] | None = None,
    config_name: str | None = None,
) -> dict:
    """Start a reel generation from one natural-language instruction. Costs credits.

    Describe what to make; the planner picks the template, avatars, and reel
    count for whatever you leave unset. Any argument you set explicitly wins
    over the planner's choice.

    Args:
        instruction: Freeform request, e.g. "make 2 reels explaining this
            paper for beginners". URLs typed here are ingested as sources.
        attachments: Extra sources: {"type": "file", "name": ..., "key": ...}
            for an uploaded file key from list_my_uploads, or
            {"type": "link", "url": ...} for a public http(s) URL.
        template_name: Optional explicit template (skips the planner's pick).
        avatar_names: Optional explicit 1-4 avatars.
        amount: Optional explicit reel count (1-7).
        enabled_tags: Optional explicit asset tags.
        config_name: Optional explicit generation config.

    Returns immediately with `series_id` and `remaining_credits`; the videos
    render in the background. Poll get_series_status until Done or Failed.
    """
    with mcp_errors("plan_reels"):
        require_scope("write")
        token = current_user_token()
        plan = PlanRequest(
            instruction=instruction,
            attachments=attachments or [],
            template_name=template_name,
            avatar_names=avatar_names,
            amount=amount,
            enabled_tags=enabled_tags,
            config_name=config_name,
        )
        with session_scope() as session:
            request = await plan_to_request(session, token["uid"], plan)
            response = create_generation(
                request=request,
                user_token=token,
                session=session,
                dispatch_task=resolve_dispatch(),
            )
        return response.model_dump()
