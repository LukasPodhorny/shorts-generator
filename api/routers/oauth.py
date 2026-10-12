"""OAuth consent and grant management for one-click MCP login.

Flow: the MCP authorize endpoint redirects the browser to the React consent
page with a short-lived request id. The page shows what the client asks for
(public `request` read: the id itself is the secret), and on approval the
frontend calls `complete` with the user's Firebase token. `complete` mints a
single-use authorization code and returns the client's redirect URL, which
the frontend navigates to. Denial works without logging in.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from mcp.server.auth.provider import construct_redirect_uri
from sqlmodel import Session, select

from api.auth import get_current_user
from api.database import get_session
from api.models import (
    OAuthAuthRequest,
    OAuthClient,
    OAuthCode,
    OAuthCompleteRequest,
    OAuthCompleteResponse,
    OAuthGrant,
    OAuthGrantRead,
    OAuthRequestRead,
)

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

CODE_TTL_SECONDS = 600


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _load_request(session: Session, request_id: str) -> OAuthAuthRequest:
    row = session.get(OAuthAuthRequest, _sha256(request_id))
    if row is None or row.expires_at <= datetime.now():
        if row is not None:
            session.delete(row)
            session.commit()
        raise HTTPException(status_code=404, detail="Authorization request not found")
    return row


def _client_name(session: Session, client_id: str) -> str | None:
    row = session.get(OAuthClient, client_id)
    if row is None:
        return None
    name = (row.data or {}).get("client_name")
    return name if isinstance(name, str) else None


@router.get("/request/{request_id}", response_model=OAuthRequestRead)
def read_auth_request(request_id: str, session: Session = Depends(get_session)):
    """Describe a pending authorization (public: the id is unguessable)."""
    row = _load_request(session, request_id)
    return OAuthRequestRead(
        request_id=request_id,
        client_id=row.client_id,
        client_name=_client_name(session, row.client_id),
        scopes=row.scope.split(),
        expires_at=row.expires_at,
    )


@router.post("/complete", response_model=OAuthCompleteResponse)
def complete_auth_request(
    body: OAuthCompleteRequest,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Approve access: mint the authorization code, return the client redirect."""
    row = _load_request(session, body.request_id)
    if session.get(OAuthClient, row.client_id) is None:
        raise HTTPException(status_code=404, detail="Authorization request not found")

    code = secrets.token_urlsafe(32)  # 256 bits
    now = datetime.now()
    session.add(
        OAuthCode(
            code_hash=_sha256(code),
            client_id=row.client_id,
            subject=user_token["uid"],
            email=user_token.get("email"),
            redirect_uri=row.redirect_uri,
            scopes=row.scope.split(),
            code_challenge=row.code_challenge,
            resource=row.resource,
            created_at=now,
            expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        )
    )
    session.delete(row)
    session.commit()
    return OAuthCompleteResponse(
        redirect_url=construct_redirect_uri(
            row.redirect_uri, code=code, state=row.state
        )
    )


@router.post("/deny", response_model=OAuthCompleteResponse)
def deny_auth_request(
    body: OAuthCompleteRequest, session: Session = Depends(get_session)
):
    """Decline access (no login needed) and return the client's error redirect."""
    row = _load_request(session, body.request_id)
    session.delete(row)
    session.commit()
    return OAuthCompleteResponse(
        redirect_url=construct_redirect_uri(
            row.redirect_uri,
            error="access_denied",
            error_description="The user declined the authorization request",
            state=row.state,
        )
    )


@router.get("/grants", response_model=list[OAuthGrantRead])
def list_grants(
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List the caller's live MCP connections ("connected apps")."""
    rows = session.exec(
        select(OAuthGrant)
        .where(OAuthGrant.subject == user_token["uid"])
        .where(OAuthGrant.revoked_at.is_(None))
        .where(OAuthGrant.expires_at > datetime.now())
        .order_by(OAuthGrant.created_at.desc())  # pyright: ignore[reportAttributeAccessIssue] -- SQLAlchemy column at runtime; checker sees datetime
    ).all()
    return [
        OAuthGrantRead.model_validate(r, from_attributes=True) for r in rows
    ]


@router.delete("/grants/{grant_id}")
def revoke_grant(
    grant_id: int,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Revoke one of the caller's MCP connections (takes effect immediately)."""
    row = session.get(OAuthGrant, grant_id)
    if row is None or row.subject != user_token["uid"] or row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found"
        )
    row.revoked_at = datetime.now()
    session.add(row)
    session.commit()
    return {"ok": True}
