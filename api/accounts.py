"""Shared account helpers used by both the REST routers and the MCP server."""

from sqlmodel import Session

from api.models import User


def get_or_create_user(session: Session, uid: str, email: str | None) -> User:
    """Fetch the user row, JIT-provisioning it (90 credits) on first sight.

    There is no signup endpoint: the first authenticated hit from a Firebase
    UID creates the row. Commits when a row is created.
    """
    user = session.get(User, uid)
    if not user:
        user = User(id=uid, email=email, credits=90)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
