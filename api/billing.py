"""Shared billing helpers used by both REST routers and the MCP server."""

import os

import stripe
from fastapi import HTTPException
from sqlmodel import Session, select

from api.accounts import get_or_create_user
from api.models import SubscriptionPlan

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

stripe.api_key = STRIPE_SECRET_KEY


def list_subscription_plans(session: Session) -> list[SubscriptionPlan]:
    """Return all subscription plans (price id, name, credits, description)."""
    return list(session.exec(select(SubscriptionPlan)).all())


def create_checkout_session_url(
    session: Session, uid: str, email: str | None, price_id: str
) -> str:
    """Create (or reuse) the Stripe customer and open a subscription Checkout.

    Returns the Checkout URL for the user to open in a browser. Credits are
    granted later by the Stripe webhook, never here.
    """
    user = get_or_create_user(session, uid, email)

    if not user.stripe_customer_id:
        # email is optional in the token (and in Stripe): omit it when unknown
        # rather than sending null.
        if email:
            customer = stripe.Customer.create(
                email=email, metadata={"user_id": uid}
            )
        else:
            customer = stripe.Customer.create(metadata={"user_id": uid})
        user.stripe_customer_id = customer.id
        session.add(user)
        session.commit()

    # Validate that the requested price exists in our DB
    plan = session.get(SubscriptionPlan, price_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid Subscription Plan")

    try:
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{FRONTEND_URL}/dashboard?success=true",
            cancel_url=f"{FRONTEND_URL}/dashboard?canceled=true",
            client_reference_id=uid,
            metadata={"plan_id": price_id},
        )
        if not checkout_session.url:
            raise HTTPException(
                status_code=502, detail="Stripe did not return a checkout URL"
            )
        return checkout_session.url
    except Exception as e:
        # Note: this also catches the 502 above and re-raises it as a 400
        # (behavior preserved from the original route; likely unintentional).
        raise HTTPException(status_code=400, detail=str(e))
