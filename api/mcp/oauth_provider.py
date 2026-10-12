"""OAuth 2.1 authorization server for one-click MCP login.

The MCP server co-hosts its own authorization server (allowed by the MCP
authorization spec). Clients register dynamically; users approve access on the
React consent page, which completes the flow with their Firebase identity, so
Google and email/password users alike keep their existing Firebase UID.

Token design:

- Authorization codes: opaque, single-use (atomically deleted on exchange),
  10-minute TTL, sha256-hashed at rest.
- Refresh tokens: JWTs whose jti is tracked in the grants table, rotated on
  every use, 30-day sliding expiry, revocable.
- Access tokens: short-lived (1 h) JWTs carrying sub/scopes plus the grant id,
  so revocation takes effect immediately via a grant-liveness check.
- `verify_token` additionally accepts raw Firebase ID tokens, preserving the
  static-Bearer [REDACTED] for local dev and header-based clients.
"""

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta

import anyio
from fastapi import HTTPException
from pydantic import AnyUrl
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.auth import OAuthProvider
from fastmcp.server.auth.jwt_issuer import JWTIssuer, derive_jwt_key
from joserfc.errors import JoseError
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.settings import (
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlmodel import Session, delete, select

from api.auth import verify_token as verify_firebase_token
from api.mcp import db as mcp_db
from api.models import OAuthAuthRequest, OAuthClient, OAuthCode, OAuthGrant

logger = logging.getLogger("pdftoreel.oauth")

SCOPES = ["read", "write"]

ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 30 * 86400
CODE_TTL_SECONDS = 600
AUTH_REQUEST_TTL_SECONDS = 600


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:8000/mcp")


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173")


def _utcnow() -> datetime:
    return datetime.now()


class PdftoreelOAuthProvider(OAuthProvider):
    """Firebase-backed OAuth provider with Postgres storage."""

    def __init__(self) -> None:
        super().__init__(
            base_url=_base_url(),
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=list(SCOPES)
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        secret = os.getenv("MCP_JWT_SECRET")
        if not secret:
            logger.warning(
                "MCP_JWT_SECRET is not set; using an insecure dev-only signing "
                "key. Set MCP_JWT_SECRET in production."
            )
            secret = "dev-only-insecure-secret"
        self._jwt = JWTIssuer(
            issuer=_base_url(),
            audience=_base_url(),
            signing_key=derive_jwt_key(
                high_entropy_material=secret, salt="pdftoreel-mcp-v1"
            ),
        )

    # -- clients ------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with Session(mcp_db.engine) as session:
            row = session.get(OAuthClient, client_id)
            if row is None:
                return None
            try:
                return OAuthClientInformationFull(**row.data)
            except Exception:
                logger.warning("Stored OAuth client %s is corrupt", client_id)
                return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        with Session(mcp_db.engine) as session:
            existing = session.get(OAuthClient, client_info.client_id)
            data = client_info.model_dump(mode="json")
            if existing is None:
                session.add(
                    OAuthClient(client_id=client_info.client_id, data=data)
                )
            else:
                existing.data = data
                session.add(existing)
            session.commit()

    # -- authorization --------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        requested = params.scopes or []
        unknown = [s for s in requested if s not in SCOPES]
        if unknown:
            raise AuthorizeError(
                error="invalid_scope",
                error_description=f"Unknown scope(s): {', '.join(unknown)}",
            )
        request_id = secrets.token_urlsafe(24)
        now = _utcnow()
        with Session(mcp_db.engine) as session:
            session.add(
                OAuthAuthRequest(
                    id=_sha256(request_id),
                    client_id=client.client_id,
                    redirect_uri=str(params.redirect_uri),
                    scope=" ".join(requested) if requested else " ".join(SCOPES),
                    state=params.state,
                    code_challenge=params.code_challenge,
                    resource=params.resource,
                    created_at=now,
                    expires_at=now + timedelta(seconds=AUTH_REQUEST_TTL_SECONDS),
                )
            )
            session.commit()
        return f"{_frontend_url()}/oauth/consent?request_id={request_id}"

    # -- codes ----------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        with Session(mcp_db.engine) as session:
            row = session.get(OAuthCode, _sha256(authorization_code))
            if row is None:
                return None
            if row.client_id != client.client_id:
                return None
            if row.expires_at <= _utcnow():
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=list(row.scopes),
                expires_at=row.expires_at.timestamp(),
                client_id=row.client_id,
                code_challenge=row.code_challenge,
                redirect_uri=AnyUrl(row.redirect_uri),
                redirect_uri_provided_explicitly=True,
                resource=row.resource,
                subject=row.subject,
            )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        # Single-use, race-safe: the code row must still exist to be consumed.
        with Session(mcp_db.engine) as session:
            code_row = session.get(OAuthCode, _sha256(authorization_code.code))
            if code_row is None or code_row.client_id != client.client_id:
                raise TokenError(
                    error="invalid_grant",
                    error_description="Authorization code is invalid or expired",
                )
            email = code_row.email
            result = session.execute(
                delete(OAuthCode).where(
                    OAuthCode.code_hash == _sha256(authorization_code.code)
                )
            )
            if result.rowcount == 0:  # consumed concurrently
                raise TokenError(
                    error="invalid_grant",
                    error_description="Authorization code is invalid or expired",
                )
            grant, refresh_token = self._issue_grant(
                session,
                client=client,
                subject=authorization_code.subject or "",
                scopes=authorization_code.scopes,
            )
            session.commit()
            access_token = self._issue_access_token(grant, email=email)
        return OAuthToken(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(grant.scopes),
            refresh_token=refresh_token,
        )

    # -- refresh --------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        try:
            payload = self._jwt.verify_token(refresh_token, expected_token_use="refresh")
        except JoseError:
            return None
        if payload.get("client_id") != client.client_id:
            return None
        with Session(mcp_db.engine) as session:
            grant = self._live_grant(session, payload.get("jti", ""), client.client_id)
            if grant is None:
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=grant.client_id,
                scopes=list(grant.scopes),
                expires_at=int(grant.expires_at.timestamp()),
                subject=grant.subject,
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if [s for s in scopes if s not in SCOPES]:
            raise TokenError(error="invalid_scope", error_description="Unknown scope requested")
        with Session(mcp_db.engine) as session:
            try:
                payload = self._jwt.verify_token(
                    refresh_token.token, expected_token_use="refresh"
                )
            except JoseError:
                raise TokenError(
                    error="invalid_grant", error_description="Invalid refresh token"
                )
            grant = self._live_grant(session, payload.get("jti", ""), client.client_id)
            if grant is None or grant.client_id != client.client_id:
                raise TokenError(
                    error="invalid_grant", error_description="Invalid refresh token"
                )
            if [s for s in scopes if s not in grant.scopes]:
                raise TokenError(
                    error="invalid_scope",
                    error_description="Requested scope exceeds grant",
                )
            new_scopes = scopes or list(grant.scopes)
            grant.scopes = new_scopes
            # Rotate: the old refresh JWT's jti stops resolving afterwards.
            new_jti = uuid.uuid4().hex
            grant.refresh_jti_hash = _sha256(new_jti)
            grant.expires_at = _utcnow() + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)
            session.add(grant)
            session.commit()
            assert grant.id is not None
            new_refresh = self._jwt.issue_refresh_token(
                client_id=grant.client_id,
                scopes=new_scopes,
                jti=new_jti,
                expires_in=REFRESH_TOKEN_TTL_SECONDS,
            )
            access_token = self._issue_access_token(grant, email=None)
        return OAuthToken(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(new_scopes),
            refresh_token=new_refresh,
        )

    # -- access ---------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            payload = self._jwt.verify_token(token, expected_token_use="access")
        except JoseError:
            return None
        grant_id = payload.get("grant_id")
        with Session(mcp_db.engine) as session:
            grant = session.get(OAuthGrant, grant_id) if grant_id else None
            if grant is None or grant.revoked_at is not None:
                return None
            if grant.expires_at <= _utcnow():
                return None
            if grant.client_id != payload.get("client_id"):
                return None
        email = payload.get("email")
        return AccessToken(
            token=token,
            client_id=payload.get("client_id", ""),
            scopes=payload.get("scope", "").split(),
            expires_at=payload.get("exp"),
            subject=payload.get("sub"),
            claims={
                "iss": payload.get("iss"),
                "email": email if isinstance(email, str) else None,
            },
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with Session(mcp_db.engine) as session:
            if isinstance(token, RefreshToken):
                try:
                    payload = self._jwt.verify_token(
                        token.token, expected_token_use="refresh"
                    )
                except JoseError:
                    return
                grant = session.exec(
                    select(OAuthGrant).where(
                        OAuthGrant.refresh_jti_hash == _sha256(payload.get("jti", ""))
                    )
                ).first()
            else:
                try:
                    payload = self._jwt.verify_token(
                        token.token, expected_token_use="access"
                    )
                except JoseError:
                    return
                grant_id = payload.get("grant_id")
                grant = session.get(OAuthGrant, grant_id) if grant_id else None
            if grant is not None and grant.revoked_at is None:
                grant.revoked_at = _utcnow()
                session.add(grant)
                session.commit()

    async def verify_token(self, token: str) -> AccessToken | None:
        access = await super().verify_token(token)
        if access is not None:
            return access
        # Fallback: raw Firebase ID tokens (local dev, header-based clients).
        try:
            decoded = await anyio.to_thread.run_sync(verify_firebase_token, token)
        except HTTPException:
            return None
        except Exception:
            logger.warning("Firebase token verification error", exc_info=True)
            return None
        uid = decoded.get("uid")
        if not uid:
            return None
        return AccessToken(
            token=token,
            client_id="firebase",
            subject=uid,
            scopes=list(SCOPES),
            expires_at=decoded.get("exp"),
            claims=dict(decoded),
        )

    # -- internals ------------------------------------------------------

    def _issue_grant(
        self,
        session: Session,
        *,
        client: OAuthClientInformationFull,
        subject: str,
        scopes: list[str],
    ) -> tuple[OAuthGrant, str]:
        now = _utcnow()
        jti = uuid.uuid4().hex
        grant = OAuthGrant(
            refresh_jti_hash=_sha256(jti),
            client_id=client.client_id,
            client_name=client.client_name,
            subject=subject,
            scopes=scopes,
            created_at=now,
            expires_at=now + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        )
        session.add(grant)
        session.flush()  # assign grant.id for the access token claim
        refresh_token = self._jwt.issue_refresh_token(
            client_id=client.client_id,
            scopes=scopes,
            jti=jti,
            expires_in=REFRESH_TOKEN_TTL_SECONDS,
        )
        return grant, refresh_token

    def _issue_access_token(self, grant: OAuthGrant, email: str | None) -> str:
        assert grant.id is not None
        return self._jwt.issue_access_token(
            client_id=grant.client_id,
            scopes=list(grant.scopes),
            jti=uuid.uuid4().hex,
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            subject=grant.subject,
            extra_claims={"grant_id": grant.id, "email": email},
        )

    def _live_grant(
        self, session: Session, jti: str, client_id: str
    ) -> OAuthGrant | None:
        if not jti:
            return None
        grant = session.exec(
            select(OAuthGrant).where(OAuthGrant.refresh_jti_hash == _sha256(jti))
        ).first()
        if grant is None:
            return None
        if grant.client_id != client_id:
            return None
        if grant.revoked_at is not None:
            return None
        if grant.expires_at <= _utcnow():
            return None
        return grant
