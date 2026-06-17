"""Chatbot-style entry point: turn one freeform message + attachments into a
generation run.

This route is a thin orchestration layer. It does NOT re-implement any
auth/credits/validation: it builds a `GenerateRequest` and hands it to the same
`create_generation(...)` the /api/generate path uses, in-process (no self-HTTP).

The work is split into two clearly separable steps -- build the request, then
commit it -- so a future confirm-gate could stop in between (return the built
request for user confirmation before spending credits) without restructuring.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlmodel import Session, select

from api.database import get_session
from api.auth import get_current_user
from api.models import (
    Avatar,
    VideoTemplate,
    GenerateRequest,
    GenerateResponse,
    PlanRequest,
)
from api.routers.generate import create_generation
from api.intent_parser import (
    PlanCatalog,
    ParsedPlan,
    IntentParseError,
    parse_intent,
)
from aishorts.modules.video_edit.video_edit_templates import EditTemplate

router = APIRouter(prefix="/api", tags=["plan"])


def _load_catalog(session: Session) -> PlanCatalog:
    """Load the template/avatar choices the parser is allowed to pick from."""
    templates: dict[str, list[str]] = {}
    for t in session.exec(select(VideoTemplate)).all():
        tags: list[str] = []
        edit_template_name = (t.data or {}).get("edit_template", "")
        if edit_template_name:
            try:
                template_cls = EditTemplate.get(edit_template_name.lower())
                tags = [a.value for a in template_cls.tag_assets]
            except ValueError:
                tags = []
        templates[t.name] = tags

    avatars: dict[str, str] = {}
    for a in session.exec(select(Avatar)).all():
        avatars[a.name] = (a.data or {}).get("instructions", "")

    return PlanCatalog(templates=templates, avatars=avatars)


def _build_request(plan: PlanRequest, parsed: ParsedPlan) -> GenerateRequest:
    """Merge the user's manual choices with the parser's inferences.

    Manual choices always win: the parser only fills what the user left unset.
    Attachments are routed straight into files/links (the parser does not pull
    them out of prose). The raw instruction is plumbed through as input_text
    programmatically -- faithfully, without LLM paraphrase -- so a prompt-only
    request still carries its topic downstream.
    """
    files = [a.key for a in plan.attachments if a.type == "file"]
    links = [a.url for a in plan.attachments if a.type == "link"]

    return GenerateRequest(
        template_name=plan.template_name or parsed.template_name,
        avatar_names=plan.avatar_names or parsed.avatar_names,
        amount=plan.amount if plan.amount is not None else parsed.amount,
        input_text=plan.instruction.strip() or None,
        files=files or None,
        links=links or None,
        config_name=plan.config_name,
        enabled_tags=(
            plan.enabled_tags if plan.enabled_tags is not None else parsed.enabled_tags
        ),
    )


@router.post("/plan", response_model=GenerateResponse)
async def plan_generation(
    plan: PlanRequest,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GenerateResponse:
    # Step 1: build the request (parse intent + merge manual choices).
    catalog = _load_catalog(session)
    try:
        parsed = await parse_intent(plan, catalog)
    except IntentParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not understand the request: {e}",
        )
    request = _build_request(plan, parsed)

    # Step 2: commit. Reuses all auth/credits/validation (file ownership, link
    # allow-listing, cost calc, atomic credit deduct) via the shared function.
    # A future confirm-gate would stop here and return `request` instead.
    return create_generation(
        request=request,
        user_token=user_token,
        session=session,
        background_tasks=background_tasks,
    )
