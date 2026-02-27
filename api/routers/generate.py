from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
import asyncio
from api.database import get_session
from api.auth import get_current_user
from api.models import (
    User,
    ReelSeries,
    Reel,
    GenerateRequest,
    ReelSeriesRead,
    GenerateResponse,
    JobStatus,
)
from api.tasks import process_reel_task

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def start_generation(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GenerateResponse:
    uid = user_token["uid"]
    email = user_token.get("email")

    # 1. Fetch User
    user = session.get(User, uid)

    if not user:
        # Create user if not exists (first login logic)
        user = User(id=uid, email=email, credits=10)
        session.add(user)
        session.commit()
        session.refresh(user)

    # 2. Check Credits
    cost = request.amount  # Assuming 1 credit per reel
    if user.credits < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient credits"
        )

    # 3. Deduct Credits
    user.credits -= cost
    session.add(user)

    # 4. Create DB Entries
    series = ReelSeries(user_id=user.id, status=JobStatus.QUEUED)
    session.add(series)
    session.commit()
    session.refresh(series)

    # Create placeholder reels
    for i in range(request.amount):
        reel = Reel(series_id=series.id, sequence_number=i + 1, status=JobStatus.QUEUED)
        session.add(reel)

    session.commit()

    # 5. Start Background Task
    background_tasks.add_task(process_reel_task, series.id, request.dict())

    return GenerateResponse(
        message="Generation started",
        series_id=series.id,
        remaining_credits=user.credits,
    )


@router.get("/status/{series_id}", response_model=ReelSeriesRead)
async def check_status(
    series_id: int, session: Session = Depends(get_session)
) -> ReelSeriesRead:
    series = session.get(ReelSeries, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return series


@router.get("/status/{series_id}/stream")
async def stream_check_status(
    series_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Streams the status of a generation series using Server-Sent Events."""
    if not session.get(ReelSeries, series_id):
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

            # Re-query the database to get the latest series state
            # This ensures we get updates committed by the background task
            series = session.exec(
                select(ReelSeries).where(ReelSeries.id == series_id)
            ).first()

            if not series:
                break  # Series was deleted mid-stream

            series_read = ReelSeriesRead.from_orm(series)
            current_state_json = series_read.json()

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
