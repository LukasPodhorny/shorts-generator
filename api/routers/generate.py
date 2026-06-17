from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import update
from sqlmodel import Session, select
import asyncio
import ipaddress
from typing import Optional
from urllib.parse import urlparse
from api.database import get_session, engine
from api.auth import get_current_user, verify_token
from api.models import (
    User,
    ReelSeries,
    Reel,
    GenerateRequest,
    ReelSeriesRead,
    GenerateResponse,
    JobStatus,
    VideoTemplate,
    UploadedFile,
)
from api.tasks import process_reel_task
from aishorts.modules.script.script import AssetType

router = APIRouter(prefix="/api", tags=["generate"])


def _validate_links(links: list[str]) -> None:
    """Reject non-http(s) links and obvious internal targets.

    Links are fetched server-side by the ingest layer, so without this a user
    could point the server at localhost or the internal network (SSRF). This
    is a basic guard, not a complete one (it does not resolve DNS).
    """
    for link in links:
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Links must be http(s) URLs: {link}",
            )
        host = parsed.hostname
        try:
            blocked = not ipaddress.ip_address(host).is_global
        except ValueError:
            blocked = host == "localhost" or host.endswith((".local", ".internal"))
        if blocked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Link target not allowed: {link}",
            )


def create_generation(
    *,
    request: GenerateRequest,
    user_token: dict,
    session: Session,
    background_tasks: BackgroundTasks,
) -> GenerateResponse:
    """Shared generation entry point used by both /api/generate and /api/plan.

    Holds all the logic the HTTP handlers must share: JIT user provisioning,
    file-ownership validation, link allow-listing/SSRF guard, template lookup +
    cost calc, atomic credit check-and-deduct, ReelSeries/Reel row creation, and
    BackgroundTasks dispatch. Callers pass a validated GenerateRequest; the
    natural-language entry point builds that request before calling here.
    """
    uid = user_token["uid"]
    email = user_token.get("email")

    # 1. Fetch User
    user = session.get(User, uid)

    if not user:
        # Create user if not exists (first login logic)
        user = User(id=uid, email=email, credits=90)
        session.add(user)
        session.commit()
        session.refresh(user)

    # 1b. Validate referenced files belong to this user. The `files` values are
    # passed straight to the LLM layer, which will fetch http(s) URLs, read
    # absolute local paths, and resolve arbitrary R2 keys. Without this check a
    # user could trigger SSRF, read server-local files (e.g. /etc/passwd,
    # credentials), or access other users' uploads, with the contents reflected
    # back into the generated reel. Only allow keys/urls the user owns.
    if request.files:
        owned = session.exec(
            select(UploadedFile).where(UploadedFile.user_id == uid)
        ).all()
        allowed_refs = {f.key for f in owned} | {f.url for f in owned}
        invalid = [f for f in request.files if f not in allowed_refs]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more referenced files were not found among your uploads.",
            )

    # 1c. Validate links: fetched server-side by the ingest layer, so only
    # allow public http(s) targets.
    if request.links:
        _validate_links(request.links)

    # 2. Fetch Template to determine cost
    statement = select(VideoTemplate).where(VideoTemplate.name == request.template_name)
    db_template = session.exec(statement).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Use the template's credit cost from database (with fallback to 1)
    unit_cost = getattr(db_template, 'credits', 1) or 1

    total_cost = request.amount * unit_cost

    # 3 + 4. Atomically check and deduct credits. The conditional UPDATE avoids
    # a read-modify-write race where concurrent requests could overdraw credits.
    result = session.execute(
        update(User)
        .where(User.id == uid, User.credits >= total_cost)
        .values(credits=User.credits - total_cost)
    )
    if result.rowcount == 0:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. This request requires {total_cost} credits."
        )

    # 5. Create DB Entries
    series = ReelSeries(user_id=user.id, status=JobStatus.QUEUED)
    session.add(series)
    session.commit()
    session.refresh(series)
    session.refresh(user)

    # Create placeholder reels
    for i in range(request.amount):
        reel = Reel(series_id=series.id, sequence_number=i + 1, status=JobStatus.QUEUED)
        session.add(reel)

    session.commit()

    # 6. Start Background Task
    background_tasks.add_task(process_reel_task, series.id, request.model_dump(), total_cost)

    return GenerateResponse(
        message="Generation started",
        series_id=series.id,
        remaining_credits=user.credits,
    )


@router.post("/generate", response_model=GenerateResponse)
async def start_generation(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GenerateResponse:
    return create_generation(
        request=request,
        user_token=user_token,
        session=session,
        background_tasks=background_tasks,
    )


@router.get("/status/{series_id}", response_model=ReelSeriesRead)
async def check_status(
    series_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReelSeriesRead:
    uid = user_token["uid"]
    series = session.get(ReelSeries, series_id)
    if not series or series.user_id != uid:
        raise HTTPException(status_code=404, detail="Series not found")

    return series


@router.get("/status/{series_id}/stream")
async def stream_check_status(
    series_id: int,
    request: Request,
    token: Optional[str] = Query(default=None),
):
    """Streams the status of a generation series using Server-Sent Events.

    Auth: accepts the Firebase JWT either as a Bearer header or as a `token`
    query parameter (the browser EventSource API cannot set headers).
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        decoded = verify_token(auth_header[7:])
    elif token:
        decoded = verify_token(token)
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = decoded["uid"]

    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        if not series or series.user_id != uid:
            raise HTTPException(status_code=404, detail="Series not found")

    async def event_generator():
        """
        Yields Server-Sent Events with the current status of the series.
        An event is sent only when the status or related data changes.
        """
        last_state_json = None
        while True:
            # Check if the client has disconnected
            if await request.is_disconnected():
                break

            # Use a fresh session per poll so updates committed by the
            # background task are visible and no connection is held between
            # polls.
            with Session(engine) as session:
                series = session.exec(
                    select(ReelSeries).where(ReelSeries.id == series_id)
                ).first()

                if not series:
                    break  # Series was deleted mid-stream

                series_read = ReelSeriesRead.model_validate(series, from_attributes=True)

            current_state_json = series_read.model_dump_json()

            # Send data only if the state has changed
            if current_state_json != last_state_json:
                yield f"data: {current_state_json}\n\n"
                last_state_json = current_state_json

            # If the job is complete, send the final status and exit the loop
            if series.status in [JobStatus.DONE, JobStatus.FAILED]:
                break

            await asyncio.sleep(2)  # Poll every 2 seconds

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/series", response_model=list[ReelSeriesRead])
async def list_user_series(
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
    offset: int = 0,
    limit: int = 10,
) -> list[ReelSeriesRead]:
    uid = user_token["uid"]
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .order_by(ReelSeries.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return session.exec(statement).all()


@router.get("/series/{series_id}", response_model=ReelSeriesRead)
async def get_series(
    series_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ReelSeriesRead:
    uid = user_token["uid"]
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .where(ReelSeries.id == series_id)
    )
    series = session.exec(statement).first()

    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return series


@router.delete("/series/{series_id}")
async def delete_user_series(  # Changed name from list_user_series
    series_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    uid = user_token["uid"]
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .where(ReelSeries.id == series_id)
    )

    # 1. Fetch the series safely
    series_to_delete = session.exec(statement).first()

    # 2. Check if it actually exists before trying to delete
    if not series_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Series not found or you don't have permission to delete it.",
        )

    # 3. Safely delete and commit
    session.delete(series_to_delete)
    session.commit()

    return {"ok": True}
