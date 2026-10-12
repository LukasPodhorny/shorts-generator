"""Request identity for MCP tools.

Tools run behind the OAuth provider (api/mcp/oauth_provider.py), which accepts
both OAuth access tokens and raw Firebase ID tokens. This helper reads the
verified identity out of the request context in the same shape the REST layer
uses, so tools can pass it straight into the shared services.
"""

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token


def current_user_token() -> dict:
    """Return the calling agent's ``{"uid": ..., "email": ...}`` token dict."""
    access = get_access_token()
    if access is None or not access.subject:
        raise ToolError("Not authenticated")
    claims = access.claims or {}
    email = claims.get("email")
    if not isinstance(email, str):
        email = None
    return {"uid": access.subject, "email": email}


def current_token_scopes() -> list[str]:
    """Return the calling token's OAuth scopes (empty when unavailable)."""
    access = get_access_token()
    if access is None:
        return []
    return list(access.scopes or [])


def require_scope(scope: str) -> None:
    """Require an OAuth scope (`read` or `write`) on the calling token."""
    access = get_access_token()
    if access is None or not access.subject:
        raise ToolError("Not authenticated")
    granted = list(access.scopes or [])
    if scope not in granted:
        have = ", ".join(granted) if granted else "none"
        raise ToolError(
            f"Requires '{scope}' access, but this connection only has: {have}. "
            "Ask the user to reconnect and approve it."
        )
