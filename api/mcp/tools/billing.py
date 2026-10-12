"""Billing tools: subscription plans and checkout (read + link only).

Credits are granted by the Stripe webhook after the user pays in their
browser; these tools never move money or grant credits directly.
"""

from api.billing import (
    create_checkout_session_url,
    list_subscription_plans as _list_plans,
)
from api.mcp.auth import current_user_token, require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors


def list_subscription_plans() -> list[dict]:
    """List the available subscription plans (name, credits, description).

    Pass a plan's `stripe_price_id` to `get_subscription_checkout_url`.
    """
    with mcp_errors("list_subscription_plans"):
        require_scope("read")
        with session_scope() as session:
            return [p.model_dump() for p in _list_plans(session)]


def get_subscription_checkout_url(price_id: str) -> dict:
    """Get a Stripe Checkout link for a subscription plan.

    Args:
        price_id: A `stripe_price_id` from `list_subscription_plans`.

    Returns `{"url": ...}`. Show the link to the user: they complete payment
    in their browser, and credits land automatically afterwards.
    """
    with mcp_errors("get_subscription_checkout_url"):
        require_scope("write")
        token = current_user_token()
        with session_scope() as session:
            url = create_checkout_session_url(
                session, token["uid"], token["email"], price_id
            )
            return {"url": url}
