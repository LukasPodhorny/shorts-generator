from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.database import get_session
from api.auth import get_current_user
from api.models import User, AddCreditsRequest, AddCreditsResponse

router = APIRouter(prefix="/api/users", tags=["users"])


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


"""
@router.post("/me")
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
"""
