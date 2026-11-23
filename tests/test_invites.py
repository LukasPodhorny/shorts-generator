"""Invite approvals must gate access before any new account receives credits."""

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from api.invites import require_invite
from api.models import User, UserRole
from api.routers.admin import InviteRequest, approve_invite, revoke_invite


def test_invite_approval_and_revocation(monkeypatch):
    monkeypatch.delenv("INVITE_ONLY", raising=False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        admin = User(id="admin", email="owner@example.com", role=UserRole.ADMIN)
        session.add(admin)
        session.commit()

        require_invite(session, "admin", "owner@example.com")
        with pytest.raises(HTTPException) as denied:
            require_invite(session, "new-user", "Guest@Example.com")
        assert denied.value.status_code == 403

        approve_invite(InviteRequest(email=" Guest@Example.com "), session, admin)
        with pytest.raises(HTTPException):
            require_invite(session, "new-user", "guest@example.com", email_verified=False)
        require_invite(session, "new-user", "guest@example.com")
        session.add(User(id="new-user", email="guest@example.com"))
        session.commit()
        require_invite(session, "new-user", None)  # Refreshed MCP token.
        revoke_invite("GUEST@example.com", session, admin)
        with pytest.raises(HTTPException):
            require_invite(session, "new-user", "guest@example.com")

        monkeypatch.setenv("INVITE_ONLY", "false")
        require_invite(session, "new-user", "guest@example.com")
