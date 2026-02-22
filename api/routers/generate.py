from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlmodel import Session, select
from api.database import get_session
from api.auth import get_current_user
from api.models import (
    User,
    ReelSeries,
    Reel,
    GenerateRequest,
    AddCreditsRequest,
    ReelSeriesRead,
    GenerateResponse,
    AddCreditsResponse,
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
    series = ReelSeries(user_id=user.id, status="Queued")
    session.add(series)
    session.commit()
    session.refresh(series)

    # Create placeholder reels
    for i in range(request.amount):
        reel = Reel(series_id=series.id, sequence_number=i + 1, status="Queued")
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


@router.get("/series", response_model=list[ReelSeriesRead])
async def list_user_series(
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ReelSeriesRead]:
    uid = user_token["uid"]
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .order_by(ReelSeries.created_at.desc())
    )
    return session.exec(statement).all()


@router.post("/add-credits", response_model=AddCreditsResponse)
async def add_credits(
    request: AddCreditsRequest,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AddCreditsResponse:
    uid = user_token["uid"]
    email = user_token.get("email")

    user = session.get(User, uid)
    if not user:
        # Create user if not exists (first login logic)
        user = User(id=uid, email=email, credits=10)
        session.add(user)

    user.credits += request.amount
    session.add(user)
    session.commit()
    session.refresh(user)

    return AddCreditsResponse(message="Credits added", total_credits=user.credits)
