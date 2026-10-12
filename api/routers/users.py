import os
import stripe
from stripe._error import SignatureVerificationError
from fastapi import APIRouter, Depends, Request, Header, HTTPException
from sqlmodel import Session, select
from api.accounts import get_or_create_user
from api.billing import create_checkout_session_url
from api.database import get_session
from api.auth import get_current_user
from api.models import (
    User,
    AddCreditsRequest,
    AddCreditsResponse,
    UserRead,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    SubscriptionPlan,
)


router = APIRouter(prefix="/api/users", tags=["users"])

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# TEMPORARILY DISABLED: add-credits endpoint disabled to prevent exploitation
# @router.post("/add-credits", response_model=AddCreditsResponse)
# async def add_credits(
#     request: AddCreditsRequest,
#     user_token: dict = Depends(get_current_user),
#     session: Session = Depends(get_session),
# ) -> AddCreditsResponse:
#     uid = user_token["uid"]
#     email = user_token.get("email")
#
#     user = session.get(User, uid)
#     if not user:
#         # Create user if not exists (first login logic)
#         user = User(id=uid, email=email, credits=90)
#         session.add(user)
#
#     user.credits += request.amount
#     session.add(user)
#     session.commit()
#     session.refresh(user)
#
#     return AddCreditsResponse(message="Credits added", total_credits=user.credits)


@router.get("/me", response_model=UserRead)
async def get_me(
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    uid = user_token["uid"]
    email = user_token.get("email")

    return get_or_create_user(session, uid, email)


@router.post("/create-checkout-session", response_model=CreateCheckoutResponse)
async def create_checkout_session(
    request: CreateCheckoutRequest,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CreateCheckoutResponse:
    uid = user_token["uid"]
    email = user_token.get("email")

    url = create_checkout_session_url(session, uid, email, request.price_id)
    return CreateCheckoutResponse(url=url)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, session: Session = Depends(get_session)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid payload or signature")

    if event["type"] == "checkout.session.completed":
        session_data = event["data"]["object"]
        uid = session_data.get("client_reference_id")
        subscription_id = session_data.get("subscription")
        plan_id = session_data.get("metadata", {}).get("plan_id")

        if uid:
            user = session.get(User, uid)
            if user:
                user.stripe_subscription_id = subscription_id
                user.subscription_status = "active"
                user.plan_id = plan_id

                plan = session.get(SubscriptionPlan, plan_id) if plan_id else None
                if plan:
                    user.credits += plan.credits
                session.add(user)
                session.commit()

    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")
        billing_reason = invoice.get("billing_reason")

        if subscription_id and billing_reason == "subscription_cycle":
            statement = select(User).where(
                User.stripe_subscription_id == subscription_id
            )
            user = session.exec(statement).first()
            if user and user.plan_id:
                plan = session.get(SubscriptionPlan, user.plan_id)
                if plan:
                    user.credits += plan.credits
                session.add(user)
                session.commit()

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        subscription_id = subscription.get("id")
        statement = select(User).where(User.stripe_subscription_id == subscription_id)
        user = session.exec(statement).first()
        if user:
            user.subscription_status = "canceled"
            session.add(user)
            session.commit()

    return {"status": "success"}
