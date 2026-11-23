"""Small invite-only access policy shared by REST and MCP."""

import os

from fastapi import HTTPException
from sqlmodel import Session

from api.models import Invite, User, UserRole


def invite_only() -> bool:
    return os.getenv("INVITE_ONLY", "true").lower() != "false"


def require_invite(
    session: Session, uid: str | None, email: str | None, *, email_verified: bool = True
) -> None:
    if not invite_only():
        return
    if not email_verified:
        raise HTTPException(status_code=403, detail="Verify your email address before using your invite.")
    user = session.get(User, uid) if uid else None
    if user and user.role == UserRole.ADMIN:
        return
    # Refreshed MCP access tokens omit email; use the provisioned account row.
    effective_email = email or (user.email if user else None)
    normalized = effective_email.strip().lower() if effective_email else ""
    if not normalized or session.get(Invite, normalized) is None:
        raise HTTPException(status_code=403, detail="PDF to Reel is invite only. Request access at support@pdftoreel.com.")
