"""Account tools: caller identity and credit balance."""

from api.accounts import get_or_create_user
from api.mcp.auth import current_user_token, require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors
from api.models import UserRead


def get_me() -> dict:
    """Return the caller's account: credit balance, role, subscription status.

    A first-time caller is provisioned with 90 free credits.
    """
    with mcp_errors("get_me"):
        require_scope("read")
        token = current_user_token()
        with session_scope() as session:
            user = get_or_create_user(session, token["uid"], token["email"])
            return UserRead.model_validate(user, from_attributes=True).model_dump(
                mode="json"
            )
