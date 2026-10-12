"""Tests for one-click OAuth login (api/mcp/oauth_provider.py, api/routers/oauth.py).

Covers the provider's storage semantics, the consent API, and a full
register -> authorize -> consent -> code -> token -> refresh -> revoke
round-trip through the real framework handlers.
"""

import asyncio
import base64
import hashlib
import os
import secrets
from urllib.parse import parse_qs, urlparse

import pytest

_ENV_BEFORE_API_IMPORT = dict(os.environ)

from fastapi import HTTPException  # noqa: E402
from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StreamableHttpTransport  # noqa: E402
from fastmcp.utilities.asgi_transport import (  # noqa: E402
    StreamingASGITransport,
    run_asgi_lifespan,
)
from mcp.server.auth.provider import (  # noqa: E402
    AuthorizationParams,
    AuthorizeError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import api.mcp.db as mcp_db  # noqa: E402
from api.auth import get_current_user  # noqa: E402
from api.database import get_session  # noqa: E402
from api.main import app  # noqa: E402
from api.mcp.oauth_provider import (  # noqa: E402
    CODE_TTL_SECONDS,
    PdftoreelOAuthProvider,
)
from api.models import OAuthClient, OAuthCode, OAuthGrant  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


def make_engine(tmp_path):
    url = f"sqlite:///{tmp_path}/oauth.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def use_engine(monkeypatch, engine):
    monkeypatch.setattr(mcp_db, "engine", engine)


def make_client_info(**overrides):
    base = dict(
        client_id="client-1",
        redirect_uris=["http://localhost:9999/callback"],
        client_name="Test Client",
        scope="read write",
    )
    base.update(overrides)
    return OAuthClientInformationFull(**base)


def make_params(**overrides):
    base = dict(
        state="xyz",
        scopes=["read", "write"],
        code_challenge="challenge",
        redirect_uri="http://localhost:9999/callback",
        redirect_uri_provided_explicitly=True,
        resource=None,
    )
    base.update(overrides)
    return AuthorizationParams(**base)


# --- provider: clients ---------------------------------------------------

def test_register_and_get_client_round_trip(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    info = make_client_info()

    async def _flow():
        assert await provider.get_client("client-1") is None
        await provider.register_client(info)
        back = await provider.get_client("client-1")
        assert back is not None
        assert back.client_id == "client-1"
        assert back.client_name == "Test Client"
        assert str(back.redirect_uris[0]) == "http://localhost:9999/callback"

    asyncio.run(_flow())


# --- provider: authorize -------------------------------------------------

def test_authorize_creates_request_and_consent_url(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()

    async def _flow():
        url = await provider.authorize(make_client_info(), make_params())
        parsed = urlparse(url)
        assert parsed.path == "/oauth/consent"
        request_id = parse_qs(parsed.query)["request_id"][0]
        assert len(request_id) >= 20
        return request_id

    request_id = asyncio.run(_flow())
    with Session(engine) as session:
        rows = session.exec(select(OAuthClient)).all()
        assert rows == []  # authorize stores the request, not the client
        from api.models import OAuthAuthRequest

        reqs = session.exec(select(OAuthAuthRequest)).all()
        assert len(reqs) == 1
        assert reqs[0].client_id == "client-1"
        assert reqs[0].code_challenge == "challenge"
        assert reqs[0].state == "xyz"


def test_authorize_rejects_unknown_scope(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()

    async def _flow():
        with pytest.raises(AuthorizeError):
            await provider.authorize(
                make_client_info(), make_params(scopes=["admin"])
            )

    asyncio.run(_flow())


# --- provider: codes -----------------------------------------------------

def _seed_code(session, code="code-1", **overrides):
    import hashlib
    from datetime import datetime, timedelta

    row = OAuthCode(
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        client_id="client-1",
        subject="u1",
        email="u1@x.com",
        redirect_uri="http://localhost:9999/callback",
        scopes=["read", "write"],
        code_challenge="challenge",
        resource=None,
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(seconds=CODE_TTL_SECONDS),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    session.add(row)
    session.commit()
    return row


def test_code_exchange_mints_tokens_and_is_single_use(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session)
    info = make_client_info()

    async def _flow():
        loaded = await provider.load_authorization_code(info, "code-1")
        assert loaded is not None
        assert loaded.subject == "u1"
        assert loaded.scopes == ["read", "write"]
        token = await provider.exchange_authorization_code(info, loaded)
        assert token.access_token
        assert token.refresh_token
        assert token.expires_in == 3600
        # Single-use: the code row is gone.
        assert await provider.load_authorization_code(info, "code-1") is None
        with pytest.raises(TokenError):
            await provider.exchange_authorization_code(info, loaded)
        return token

    token = asyncio.run(_flow())
    access = asyncio.run(provider.load_access_token(token.access_token))
    assert access is not None
    assert access.subject == "u1"
    assert access.scopes == ["read", "write"]
    assert access.claims["email"] == "u1@x.com"


def test_code_exchange_rejects_wrong_client_and_expired(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session, code="c1")
        _seed_code(
            session,
            code="old",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
    info = make_client_info()
    other = make_client_info(client_id="client-2")

    async def _flow():
        assert await provider.load_authorization_code(info, "nope") is None
        assert await provider.load_authorization_code(other, "c1") is None
        assert await provider.load_authorization_code(info, "old") is None

    asyncio.run(_flow())


# --- provider: refresh ---------------------------------------------------

def test_refresh_rotates_and_rejects_reuse_and_escalation(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session)
    info = make_client_info()

    async def _flow():
        loaded = await provider.load_authorization_code(info, "code-1")
        first = await provider.exchange_authorization_code(info, loaded)
        stored = await provider.load_refresh_token(info, first.refresh_token)
        assert stored is not None
        # Narrowing scopes is allowed.
        second = await provider.exchange_refresh_token(info, stored, ["read"])
        assert second.refresh_token != first.refresh_token
        # Old refresh token is dead after rotation.
        assert await provider.load_refresh_token(info, first.refresh_token) is None
        # Escalation beyond the grant is rejected.
        stored2 = await provider.load_refresh_token(info, second.refresh_token)
        with pytest.raises(TokenError):
            await provider.exchange_refresh_token(info, stored2, ["write"])

    asyncio.run(_flow())


# --- provider: access + revoke -------------------------------------------

def test_access_token_rejects_revoked_and_garbage(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session)
    info = make_client_info()

    async def _flow():
        loaded = await provider.load_authorization_code(info, "code-1")
        token = await provider.exchange_authorization_code(info, loaded)
        assert await provider.load_access_token(token.access_token) is not None
        assert await provider.load_access_token("garbage") is None
        # Revoke via the refresh token: the access token dies immediately.
        stored = await provider.load_refresh_token(info, token.refresh_token)
        await provider.revoke_token(stored)
        assert await provider.load_access_token(token.access_token) is None
        assert await provider.load_refresh_token(info, token.refresh_token) is None
        return token

    token = asyncio.run(_flow())
    # Revoking an invalid token is a no-op, not an error.
    from mcp.server.auth.provider import RefreshToken as RefreshTokenModel

    asyncio.run(
        provider.revoke_token(
            RefreshTokenModel(token="nope", client_id="client-1", scopes=[])
        )
    )
    assert token.access_token  # silence linters about unused


def test_revoke_via_access_token(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session)
    info = make_client_info()

    async def _flow():
        loaded = await provider.load_authorization_code(info, "code-1")
        token = await provider.exchange_authorization_code(info, loaded)
        access = await provider.load_access_token(token.access_token)
        await provider.revoke_token(access)
        assert await provider.load_access_token(token.access_token) is None

    asyncio.run(_flow())


# --- provider: Firebase fallback -----------------------------------------

def test_verify_token_accepts_oauth_and_firebase(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session)
    info = make_client_info()
    monkeypatch.setattr(
        "api.mcp.oauth_provider.verify_firebase_token",
        lambda token: {"uid": "fb-u", "email": "fb@x.com", "exp": 9999999999},
    )

    async def _flow():
        loaded = await provider.load_authorization_code(info, "code-1")
        token = await provider.exchange_authorization_code(info, loaded)
        oauth_access = await provider.verify_token(token.access_token)
        assert oauth_access is not None and oauth_access.subject == "u1"
        fb_access = await provider.verify_token("firebase-id-token")
        assert fb_access is not None and fb_access.subject == "fb-u"
        assert fb_access.scopes == ["read", "write"]

    asyncio.run(_flow())


def test_verify_token_fails_closed(tmp_path, monkeypatch):
    from fastapi import HTTPException as FastHTTPException

    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()

    def _raise(token):
        raise FastHTTPException(status_code=401, detail="nope")

    monkeypatch.setattr("api.mcp.oauth_provider.verify_firebase_token", _raise)

    async def _flow():
        assert await provider.verify_token("bad") is None

    asyncio.run(_flow())


# --- consent API ---------------------------------------------------------

def _override_rest(engine, uid="u1"):
    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": uid,
        "email": f"{uid}@x.com",
    }


def _pending_request_id(engine):
    from api.models import OAuthAuthRequest

    provider = PdftoreelOAuthProvider()
    url = asyncio.run(provider.authorize(make_client_info(), make_params()))
    return urlparse(url).query.split("request_id=")[1]


def test_consent_complete_and_deny(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    with Session(engine) as session:
        session.add(
            OAuthClient(client_id="client-1", data=make_client_info().model_dump(mode="json"))
        )
        session.commit()
    request_id = _pending_request_id(engine)
    _override_rest(engine)
    try:
        client = TestClient(app)
        desc = client.get(f"/api/oauth/request/{request_id}")
        assert desc.status_code == 200
        assert desc.json()["client_name"] == "Test Client"
        assert desc.json()["scopes"] == ["read", "write"]
        assert client.get("/api/oauth/request/nope").status_code == 404

        done = client.post("/api/oauth/complete", json={"request_id": request_id})
        assert done.status_code == 200, done.text
        redirect = urlparse(done.json()["redirect_url"])
        assert redirect.hostname == "localhost"
        query = parse_qs(redirect.query)
        assert query["state"] == ["xyz"]
        assert len(query["code"][0]) > 20
        # Single-use: consumed requests are gone.
        assert (
            client.post("/api/oauth/complete", json={"request_id": request_id}).status_code
            == 404
        )

        deny_id = _pending_request_id(engine)
        denied = client.post("/api/oauth/deny", json={"request_id": deny_id})
        assert denied.status_code == 200
        denied_query = parse_qs(urlparse(denied.json()["redirect_url"]).query)
        assert denied_query["error"] == ["access_denied"]
        assert denied_query["state"] == ["xyz"]
    finally:
        app.dependency_overrides.clear()


def test_complete_requires_login(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    request_id = _pending_request_id(engine)
    app.dependency_overrides[get_session] = lambda: iter([Session(engine)])
    try:
        response = TestClient(app).post(
            "/api/oauth/complete", json={"request_id": request_id}
        )
        assert response.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


def test_grants_list_and_revoke_scoped_to_user(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    provider = PdftoreelOAuthProvider()
    with Session(engine) as session:
        _seed_code(session, code="c1")
        _seed_code(session, code="c2")

    async def _grant():
        info = make_client_info()
        for code in ("c1", "c2"):
            loaded = await provider.load_authorization_code(info, code)
            await provider.exchange_authorization_code(info, loaded)

    asyncio.run(_grant())
    _override_rest(engine, uid="u1")
    try:
        client = TestClient(app)
        grants = client.get("/api/oauth/grants").json()
        assert len(grants) == 2
        assert grants[0]["client_id"] == "client-1"
        assert "token" not in str(grants).lower()  # no token material leaked
        first_id = grants[0]["id"]
        assert client.delete(f"/api/oauth/grants/{first_id}").status_code == 200
        assert len(client.get("/api/oauth/grants").json()) == 1
        assert client.delete("/api/oauth/grants/9999").status_code == 404
    finally:
        app.dependency_overrides.clear()

    _override_rest(engine, uid="someone-else")
    try:
        client = TestClient(app)
        assert client.get("/api/oauth/grants").json() == []
        remaining = None
        with Session(engine) as session:
            rows = session.exec(select(OAuthGrant)).all()
            remaining = [r.id for r in rows if r.revoked_at is None]
        assert len(remaining) == 1
        assert client.delete(f"/api/oauth/grants/{remaining[0]}").status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- full round-trip -----------------------------------------------------

def test_full_oauth_round_trip(tmp_path, monkeypatch):
    """Register -> authorize -> consent -> code -> token -> tool -> refresh -> revoke."""
    import httpx2

    engine = make_engine(tmp_path)
    use_engine(monkeypatch, engine)
    _override_rest(engine)
    try:
        client = TestClient(app)
        reg = client.post(
            "/mcp/register",
            json={
                "redirect_uris": ["http://localhost:9999/callback"],
                "token_endpoint_auth_method": "none",
                "client_name": "E2E Client",
                "scope": "read write",
            },
        )
        assert reg.status_code in (200, 201), reg.text
        client_id = reg.json()["client_id"]

        verifier = secrets.token_urlsafe(32)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        auth = client.get(
            "/mcp/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://localhost:9999/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "s123",
                "scope": "read write",
            },
            follow_redirects=False,
        )
        assert auth.status_code in (302, 307), auth.text
        request_id = parse_qs(urlparse(auth.headers["location"]).query)["request_id"][0]

        done = client.post("/api/oauth/complete", json={"request_id": request_id})
        assert done.status_code == 200, done.text
        query = parse_qs(urlparse(done.json()["redirect_url"]).query)
        assert query["state"] == ["s123"]

        tok = client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": "http://localhost:9999/callback",
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        tokens = tok.json()
        assert tokens["token_type"] == "Bearer"

        # Wrong verifier must fail.
        bad = client.post(
            "/mcp/token",
            data={
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": "http://localhost:9999/callback",
                "client_id": client_id,
                "code_verifier": "wrong",
            },
        )
        assert bad.status_code in (400, 401)

        async def _use_token(access_token):
            def factory(**kwargs):
                return httpx2.AsyncClient(
                    transport=StreamingASGITransport(app), **kwargs
                )

            transport = StreamableHttpTransport(
                url="http://testserver/mcp",
                auth=access_token,
                httpx_client_factory=factory,
            )
            async with run_asgi_lifespan(app):
                async with Client(transport) as mcp_client:
                    me = await mcp_client.call_tool("get_me", {})
                    return me.content[0].text

        me_text = asyncio.run(_use_token(tokens["access_token"]))
        assert '"id":"u1"' in me_text.replace(" ", "")
        assert '"credits":90' in me_text.replace(" ", "")

        ref = client.post(
            "/mcp/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )
        assert ref.status_code == 200, ref.text
        refreshed = ref.json()
        assert refreshed["refresh_token"] != tokens["refresh_token"]

        grants = client.get("/api/oauth/grants").json()
        assert len(grants) == 1
        assert (
            client.delete(f"/api/oauth/grants/{grants[0]['id']}").status_code == 200
        )
        with pytest.raises(Exception):
            asyncio.run(_use_token(tokens["access_token"]))
    finally:
        app.dependency_overrides.clear()
