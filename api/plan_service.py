"""Natural-language planning orchestration shared by REST and MCP entry points.

This module holds the pure orchestration behind ``POST /api/plan`` (resolve
sources, ingest them, parse intent, build a ``GenerateRequest``) so the MCP
``plan_reels`` tool can reuse it without going through HTTP.
"""

from fastapi import HTTPException, status
from sqlmodel import Session, select

from aishorts.modules.video_edit.video_edit_templates import EditTemplate
from api.intent_parser import (
    IntentParseError,
    ParsedPlan,
    PlanCatalog,
    parse_intent,
)
from api.models import (
    Avatar,
    GenerateRequest,
    PlanRequest,
    UploadedFile,
    VideoTemplate,
)
from api.source_ingest import (
    MAX_SOURCE_LINKS,
    SourceIngestError,
    build_plan_input_text,
    extract_links,
    ingest_sources,
    is_public_http_url,
    merge_links,
)

def load_plan_catalog(session: Session) -> PlanCatalog:
    """Load the template/avatar choices the parser is allowed to pick from."""
    templates: dict[str, list[str]] = {}
    descriptions: dict[str, str] = {}
    for t in session.exec(select(VideoTemplate)).all():
        tags: list[str] = []
        edit_template_name = (t.data or {}).get("edit_template", "")
        if edit_template_name:
            try:
                template_cls = EditTemplate.get(edit_template_name.lower())
                tags = [a.value for a in template_cls.tag_assets]
                descriptions[t.name] = template_cls.description
            except ValueError:
                tags = []
        templates[t.name] = tags

    avatars: dict[str, str] = {}
    for a in session.exec(select(Avatar)).all():
        avatars[a.name] = (a.data or {}).get("instructions", "")

    return PlanCatalog(templates=templates, avatars=avatars, template_descriptions=descriptions)


def validate_owned_files(session: Session, uid: str, file_keys: list[str]) -> None:
    """Reject attached file keys the user does not own.

    The keys are fetched server-side during ingestion, so this guards against
    pointing the ingester at another user's uploads.
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


def resolve_plan_sources(plan: PlanRequest) -> tuple[list[str], list[str]]:
    """Work out which files and links to ingest for this request.

    Files come only from UI attachments. Links are the union of UI-attached
    links and any URLs the user typed into the instruction (extracted by regex,
    not by the LLM). Invalid links are reported before generation starts.
    """
    ui_files = [a.key for a in plan.attachments if a.type == "file"]
    ui_links = [a.url for a in plan.attachments if a.type == "link"]
    prose_links = extract_links(plan.instruction)

    links = merge_links(ui_links, prose_links)
    if len(links) > MAX_SOURCE_LINKS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"You can use up to {MAX_SOURCE_LINKS} links per request.",
        )
    if any(not is_public_http_url(url) for url in links):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Links must be public http(s) URLs.",
        )

    return ui_files, links


def build_generate_request(
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


async def plan_to_request(
    session: Session, uid: str, plan: PlanRequest
) -> GenerateRequest:
    """Turn one freeform message + attachments into a validated GenerateRequest.

    Stops before spending credits: the caller commits the returned request via
    ``create_generation``.
    """
    # Step 1: resolve + ingest sources at the API level. Links are pulled from
    # the prose by regex (no LLM), unioned with UI-attached links, and ingested
    # together with attached files into one Markdown blob. The core library
    # never sees the files/links -- only the resulting text.
    files, links = resolve_plan_sources(plan)
    if not plan.instruction.strip() and not files and not links:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Type a request or add a file or link first.",
        )
    validate_owned_files(session, uid, files)
    try:
        source_markdown = await ingest_sources(files, links)
    except SourceIngestError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    input_text = build_plan_input_text(plan.instruction, source_markdown)

    # Step 2: parse intent (config only) and merge manual choices. The ingested
    # source preview helps the parser judge topic/audience; it routes nothing.
    catalog = load_plan_catalog(session)
    try:
        parsed = await parse_intent(plan, catalog, source_preview=source_markdown)
    except IntentParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not understand the request: {e}",
        )
    return build_generate_request(plan, parsed, input_text)
