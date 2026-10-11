"""Chatbot-style entry point: turn one freeform message + attachments into a
generation run.

This route is a thin orchestration layer. It does NOT re-implement any
auth/credits/validation: it builds a `GenerateRequest` and hands it to the same
`create_generation(...)` the /api/generate path uses, in-process (no self-HTTP).

The work is split into two clearly separable steps -- build the request, then
commit it -- so a future confirm-gate could stop in between (return the built
request for user confirmation before spending credits) without restructuring.
"""

import logging

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlmodel import Session, select

from api.database import get_session
from api.auth import get_current_user
from api.models import (
    Avatar,
    UploadedFile,
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
from api.source_ingest import (
    build_plan_input_text,
    extract_links,
    ingest_sources,
    is_public_http_url,
    merge_links,
)
from aishorts.modules.video_edit.video_edit_templates import EditTemplate

logger = logging.getLogger("ShortsGenerator.Plan")

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


def _validate_owned_files(session: Session, uid: str, file_keys: list[str]) -> None:
    """Reject attached file keys the user does not own.

    The keys are fetched server-side during ingestion, so this guards against
    pointing the ingester at another user's uploads. (On /api/generate the same
    check lives in create_generation, but here we ingest before that runs.)
    """
    if not file_keys:
        return
    owned = session.exec(
        select(UploadedFile).where(UploadedFile.user_id == uid)
    ).all()
    allowed = {f.key for f in owned} | {f.url for f in owned}
    invalid = [k for k in file_keys if k not in allowed]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more attached files were not found among your uploads.",
        )


def _resolve_sources(plan: PlanRequest) -> tuple[list[str], list[str]]:
    """Work out which files and links to ingest for this request.

    Files come only from UI attachments. Links are the union of UI-attached
    links and any URLs the user typed into the instruction (extracted by regex,
    not by the LLM). Unsafe/internal link targets are dropped rather than
    failing the whole message, since a URL can show up casually in prose.
    """
    ui_files = [a.key for a in plan.attachments if a.type == "file"]
    ui_links = [a.url for a in plan.attachments if a.type == "link"]
    prose_links = extract_links(plan.instruction)

    links = merge_links(ui_links, prose_links)
    safe_links = [u for u in links if is_public_http_url(u)]
    dropped = [u for u in links if u not in safe_links]
    if dropped:
        logger.warning("Dropping unsafe/internal link targets: %s", dropped)

    return ui_files, safe_links


def _build_request(
    plan: PlanRequest, parsed: ParsedPlan, input_text: str | None
) -> GenerateRequest:
    """Merge the user's manual choices with the parser's inferences.

    Manual choices always win: the parser only fills what the user left unset.
    Sources are already ingested into ``input_text`` at the API level, so the
    core library is handed text only -- files and links are left blank, exactly
    as the parser never touches them.
    """
    return GenerateRequest(
        template_name=plan.template_name or parsed.template_name,
        avatar_names=plan.avatar_names or parsed.avatar_names,
        amount=plan.amount if plan.amount is not None else parsed.amount,
        input_text=input_text,
        files=None,
        links=None,
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
    uid = user_token["uid"]

    # Step 1: resolve + ingest sources at the API level. Links are pulled from
    # the prose by regex (no LLM), unioned with UI-attached links, and ingested
    # together with attached files into one Markdown blob. The core library
    # never sees the files/links -- only the resulting text.
    files, links = _resolve_sources(plan)
    _validate_owned_files(session, uid, files)
    source_markdown = await ingest_sources(files, links)
    input_text = build_plan_input_text(plan.instruction, source_markdown)

    # Step 2: parse intent (config only) and merge manual choices. The ingested
    # source preview helps the parser judge topic/audience; it routes nothing.
    catalog = _load_catalog(session)
    try:
        parsed = await parse_intent(plan, catalog, source_preview=source_markdown)
    except IntentParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not understand the request: {e}",
        )
    request = _build_request(plan, parsed, input_text)

    # Step 3: commit. Reuses all auth/credits/validation (cost calc, atomic
    # credit deduct) via the shared function. files/links are blank here, so its
    # ownership/SSRF checks are no-ops -- we validated and ingested already.
    # A future confirm-gate would stop here and return `request` instead.
    return create_generation(
        request=request,
        user_token=user_token,
        session=session,
        background_tasks=background_tasks,
    )
