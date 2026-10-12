"""Tests for the MCP server (api/mcp) and the shared services behind it.

Covers: the Firebase token verifier, the shared account/catalog/series/upload
services, the decoupled ``create_generation`` dispatch, the plan-service
orchestration, MCP tool registration, one end-to-end MCP-over-HTTP flow, and
REST regression for the refactored routers.

All database work runs against throwaway SQLite files; the production
``engine`` is never touched (the MCP suite patches ``api.mcp.db.engine`` and
the REST tests override the ``get_session`` dependency).
"""

import asyncio
import os

import pytest

# Importing `api.*` runs `load_dotenv()`, which would leak the developer's real
# `.env` into this pytest process. Snapshot and restore around the import so
# this module leaves no trace for siblings (same pattern as test_api_guards).
_ENV_BEFORE_API_IMPORT = dict(os.environ)

from fastapi import HTTPException  # noqa: E402
from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StreamableHttpTransport  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from fastmcp.server.auth import AccessToken  # noqa: E402
from fastmcp.utilities.asgi_transport import (  # noqa: E402
    StreamingASGITransport,
    run_asgi_lifespan,
)
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from api import catalog as catalog_service  # noqa: E402
from api import series as series_service  # noqa: E402
from api import uploads as uploads_service  # noqa: E402
from api.accounts import get_or_create_user  # noqa: E402
from api.auth import get_current_user  # noqa: E402
from api.database import get_session  # noqa: E402
from api.main import app  # noqa: E402
from api.mcp.auth import current_user_token  # noqa: E402
from api.mcp.oauth_provider import PdftoreelOAuthProvider  # noqa: E402
from api.mcp.server import mcp  # noqa: E402
from api.models import (  # noqa: E402
    AttachedFile,
    AttachedLink,
    Avatar,
    GenerateRequest,
    GenerationConfig,
    PlanRequest,
    ReelSeries,
    UploadedFile,
    User,
    VideoTemplate,
)
from api.plan_service import (  # noqa: E402
    build_generate_request,
    plan_to_request,
    resolve_plan_sources,
)

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    # These tests cover in-process dispatch; the RQ path has its own suite.
    monkeypatch.delenv("REDIS_URL", raising=False)


# --- helpers ---------------------------------------------------------------

def make_engine(tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def seed_catalog(session):
    session.add(
        Avatar(
            name="narrator",
            data={"instructions": "Calm explainer", "voice": {"provider": "test"}},
        )
    )
    session.add(
        VideoTemplate(
            name="basic", data={"edit_template": "gameplay"}, credits=2
        )
    )
    session.add(
        VideoTemplate(
            name="broken", data={"edit_template": "missing-template"}, credits=1
        )
    )
    session.add(GenerationConfig(name="default", data={}, is_default=True))
    session.commit()


def seed_series(session, uid="u1"):
    series = ReelSeries(user_id=uid, status="Queued")
    session.add(series)
    session.commit()
    session.refresh(series)
    return series


# --- request identity --------------------------------------------------------

# Token verification itself moved to the OAuth provider; its coverage lives in
# tests/test_mcp_oauth.py (OAuth tokens and the Firebase fallback).


def test_current_user_token_requires_auth_context():
    with pytest.raises(ToolError):
        current_user_token()


# --- OAuth endpoint rate limiting ------------------------------------------

class _FakeCounter:
    def __init__(self):
        self.hits = {}

    def hit(self, key):
        self.hits[key] = self.hits.get(key, 0) + 1
        return self.hits[key]


def _run_middleware(middleware, path="/token", ip="1.2.3.4"):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {
        "type": "http",
        "path": path,
        "headers": [(b"x-forwarded-for", ip.encode())],
        "client": (ip, 1234),
    }

    async def _flow():
        await middleware(scope, receive, send)

    asyncio.run(_flow())
    return sent


def test_rate_limit_middleware_throttles_and_passes_through(monkeypatch):
    from api.mcp.ratelimit import RateLimitMiddleware

    monkeypatch.setenv("MCP_AUTH_RATE_LIMIT_PER_MINUTE", "2")
    store = _FakeCounter()

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RateLimitMiddleware(downstream, store=store)
    assert _run_middleware(middleware)[0]["status"] == 200
    assert _run_middleware(middleware)[0]["status"] == 200
    limited = _run_middleware(middleware)
    assert limited[0]["status"] == 429
    assert dict(limited[0]["headers"])[b"retry-after"] == b"60"
    # Other paths and other clients are unaffected.
    assert _run_middleware(middleware, path="/") == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"ok"},
    ]
    assert _run_middleware(middleware, ip="9.9.9.9")[0]["status"] == 200
    assert all(key.startswith("mcp:rl:/token:") for key in store.hits)


def test_rate_limit_middleware_fails_open_without_redis(monkeypatch):
    from api.mcp.ratelimit import RateLimitMiddleware, build_store

    monkeypatch.delenv("REDIS_URL", raising=False)
    assert build_store() is None

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    assert _run_middleware(RateLimitMiddleware(downstream))[0]["status"] == 200

    class _BrokenStore:
        def hit(self, key):
            raise RuntimeError("redis down")

    assert _run_middleware(RateLimitMiddleware(downstream, store=_BrokenStore()))[0][
        "status"
    ] == 200


# --- tool error mapping + logging -----------------------------------------

def test_mcp_errors_logs_outcome(caplog):
    from api.mcp.errors import mcp_errors

    with caplog.at_level("INFO", logger="pdftoreel.mcp"):
        with mcp_errors("demo_tool"):
            pass
    assert "tool=demo_tool outcome=ok" in caplog.text

    caplog.clear()
    with caplog.at_level("INFO", logger="pdftoreel.mcp"):
        try:
            with mcp_errors("demo_tool"):
                raise HTTPException(status_code=402, detail="poor")
        except Exception as e:
            assert "402" in str(e)
    assert "tool=demo_tool outcome=http_402" in caplog.text


# --- services --------------------------------------------------------------

def test_get_or_create_user_provisions_90_credits(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        user = get_or_create_user(session, "new-uid", "n@x.com")
        assert user.credits == 90
        again = get_or_create_user(session, "new-uid", "n@x.com")
        assert again.id == user.id
        assert session.get(User, "new-uid").credits == 90


def test_catalog_templates_resolve_tags_with_fallback(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        templates = {t.name: t for t in catalog_service.list_video_templates(session)}
        assert templates["basic"].credits == 2
        assert len(templates["basic"].tags) > 0
        assert all(isinstance(t.asset_type, str) for t in templates["basic"].tags)
        # Unknown edit_template degrades to no tags instead of raising.
        assert templates["broken"].tags == []


def test_generation_config_data_stays_internal(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        from api.models import GenerationConfigRead

        reads = [
            GenerationConfigRead.model_validate(c, from_attributes=True)
            for c in catalog_service.list_generation_configs(session)
        ]
        assert reads[0].name == "default"
        assert "data" not in reads[0].model_dump()


def test_series_scoping_hides_other_users(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        mine = seed_series(session, "u1")
        seed_series(session, "u2")
        assert series_service.get_user_series(session, "u1", mine.id).id == mine.id
        with pytest.raises(HTTPException) as exc:
            series_service.get_user_series(session, "u2", mine.id)
        assert exc.value.status_code == 404
        assert [s.id for s in series_service.list_user_series(session, "u1")] == [mine.id]
        with pytest.raises(HTTPException):
            series_service.delete_user_series(session, "u2", mine.id)
        series_service.delete_user_series(session, "u1", mine.id)
        assert session.get(ReelSeries, mine.id) is None


def test_uploads_list_scoped_to_user(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        get_or_create_user(session, "u2", None)
        session.add(
            UploadedFile(
                filename="a.pdf", url="http://x/a", key="k1",
                content_type="application/pdf", user_id="u1",
            )
        )
        session.add(
            UploadedFile(
                filename="b.pdf", url="http://x/b", key="k2",
                content_type="application/pdf", user_id="u2",
            )
        )
        session.commit()
        assert [f.key for f in uploads_service.list_user_uploads(session, "u1")] == ["k1"]


# --- create_generation dispatch --------------------------------------------

def test_create_generation_with_dispatch_task(tmp_path):
    from api.routers.generate import create_generation

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        dispatched = []
        response = create_generation(
            request=GenerateRequest(
                template_name="basic",
                avatar_names=["narrator"],
                amount=2,
                input_text="hello",
            ),
            user_token={"uid": "u1", "email": "u1@x.com"},
            session=session,
            dispatch_task=lambda sid, data, cost: dispatched.append((sid, data, cost)),
        )
        assert response.remaining_credits == 90 - 2 * 2
        assert len(dispatched) == 1
        series_id, data, cost = dispatched[0]
        assert series_id == response.series_id
        assert cost == 4
        assert data["input_text"] == "hello"
        stored = session.get(ReelSeries, series_id)
        assert stored is not None and stored.user_id == "u1"


def test_create_generation_guards_unchanged(tmp_path):
    from api.routers.generate import create_generation

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        base = dict(
            user_token={"uid": "u1"},
            session=session,
            dispatch_task=lambda *a: None,
        )
        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="nope", avatar_names=["narrator"]
                ),
                **base,
            )
        assert exc.value.status_code == 404

        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="basic",
                    avatar_names=["narrator"],
                    files=["someone-elses-key"],
                ),
                **base,
            )
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="basic",
                    avatar_names=["narrator"],
                    links=["http://localhost:9/internal"],
                ),
                **base,
            )
        assert exc.value.status_code == 400

        get_or_create_user(session, "poor", None)
        session.add(
            VideoTemplate(
                name="pricey", data={"edit_template": "gameplay"}, credits=100
            )
        )
        session.commit()

        def _must_not_dispatch(*args):
            raise AssertionError("must not dispatch without credits")

        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="pricey", avatar_names=["narrator"]
                ),
                user_token={"uid": "poor"},
                session=session,
                dispatch_task=_must_not_dispatch,
            )
        assert exc.value.status_code == 402

        with pytest.raises(ValueError):
            create_generation(
                request=GenerateRequest(
                    template_name="basic", avatar_names=["narrator"]
                ),
                user_token={"uid": "u1"},
                session=session,
            )


def test_create_generation_enforces_concurrency_cap(tmp_path, monkeypatch):
    from api.routers.generate import create_generation

    monkeypatch.delenv("MAX_CONCURRENT_GENERATIONS_PER_USER", raising=False)
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        get_or_create_user(session, "u1", None)
        session.add(ReelSeries(user_id="u1", status="Queued"))
        session.add(ReelSeries(user_id="u1", status="Processing"))
        session.add(ReelSeries(user_id="u1", status="Done"))
        session.add(ReelSeries(user_id="u2", status="Queued"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="basic", avatar_names=["narrator"]
                ),
                user_token={"uid": "u1"},
                session=session,
                dispatch_task=lambda *a: None,
            )
        assert exc.value.status_code == 429
        # Other users are unaffected, and finishing one job reopens the slot.
        create_generation(
            request=GenerateRequest(
                template_name="basic", avatar_names=["narrator"]
            ),
            user_token={"uid": "u2"},
            session=session,
            dispatch_task=lambda *a: None,
        )
        from sqlalchemy import update as sa_update

        session.exec(
            sa_update(ReelSeries)
            .where(ReelSeries.user_id == "u1")
            .values(status="Done")
        )
        session.commit()
        create_generation(
            request=GenerateRequest(
                template_name="basic", avatar_names=["narrator"]
            ),
            user_token={"uid": "u1"},
            session=session,
            dispatch_task=lambda *a: None,
        )


# --- plan service ----------------------------------------------------------

def test_resolve_plan_sources_extracts_and_filters_links():
    plan = PlanRequest(
        instruction="Explain https://example.com/paper and http://localhost:9/x",
        attachments=[
            AttachedFile(type="file", name="a.pdf", key="k1"),
            AttachedLink(type="link", url="https://ui.example/z"),
        ],
    )
    files, links = resolve_plan_sources(plan)
    assert files == ["k1"]
    assert links == ["https://ui.example/z", "https://example.com/paper"]


def test_build_generate_request_manual_choices_win():
    from api.intent_parser import ParsedPlan

    plan = PlanRequest(
        instruction="x", template_name="manual", amount=3, avatar_names=["a1"]
    )
    parsed = ParsedPlan(
        template_name="parsed", avatar_names=["a2"], amount=1, enabled_tags=["song"]
    )
    request = build_generate_request(plan, parsed, "text")
    assert request.template_name == "manual"
    assert request.amount == 3
    assert request.avatar_names == ["a1"]
    assert request.enabled_tags == ["song"]
    assert request.files is None and request.links is None


def test_plan_to_request_orchestrates_ingest_and_parse(tmp_path, monkeypatch):
    from api.intent_parser import ParsedPlan

    async def fake_ingest(files, links):
        assert files == ["k1"]
        return "## markdown"

    async def fake_parse(plan, catalog, source_preview=None):
        assert source_preview == "## markdown"
        assert "basic" in catalog.templates
        return ParsedPlan(template_name="basic", avatar_names=["narrator"], amount=2)

    monkeypatch.setattr("api.plan_service.ingest_sources", fake_ingest)
    monkeypatch.setattr("api.plan_service.parse_intent", fake_parse)

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        get_or_create_user(session, "u1", None)
        session.add(
            UploadedFile(
                filename="a.pdf", url="http://x/a", key="k1",
                content_type="application/pdf", user_id="u1",
            )
        )
        session.commit()
        plan = PlanRequest(
            instruction="make it",
            attachments=[AttachedFile(type="file", name="a.pdf", key="k1")],
        )
        request = asyncio.run(plan_to_request(session, "u1", plan))
        assert request.template_name == "basic"
        assert request.amount == 2
        assert "make it" in (request.input_text or "")
        assert "## markdown" in (request.input_text or "")


def test_plan_to_request_rejects_unowned_files(tmp_path, monkeypatch):
    async def _nope(*a, **k):
        raise AssertionError("must not ingest unowned files")

    monkeypatch.setattr("api.plan_service.ingest_sources", _nope)
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        plan = PlanRequest(
            instruction="x",
            attachments=[AttachedFile(type="file", name="a.pdf", key="nope")],
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(plan_to_request(session, "u1", plan))
        assert exc.value.status_code == 400


# --- MCP wiring ------------------------------------------------------------

EXPECTED_TOOLS = {
    "list_avatars",
    "list_video_templates",
    "list_generation_configs",
    "get_me",
    "list_my_uploads",
    "upload_file",
    "delete_my_upload",
    "generate_reels",
    "plan_reels",
    "get_series_status",
    "list_my_series",
    "delete_my_series",
    "list_subscription_plans",
    "get_subscription_checkout_url",
}


def test_all_tools_registered():
    async def _list():
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = asyncio.run(_list())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    plan = next(t for t in tools if t.name == "plan_reels")
    assert "attachments" in plan.input_schema["properties"]


def test_mcp_http_end_to_end(tmp_path, monkeypatch):
    """Full flow through the mounted app: auth, credits, generate, status."""
    import httpx2

    import api.mcp.db as mcp_db

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
    monkeypatch.setattr(mcp_db, "engine", engine)

    async def fake_verify(self, token):
        if token != "good-token":
            return None
        return AccessToken(
            token=token,
            client_id="firebase",
            subject="agent-uid",
            scopes=["read", "write"],
            claims={"email": "a@x.com"},
        )

    monkeypatch.setattr(PdftoreelOAuthProvider, "verify_token", fake_verify)

    dispatched = []
    monkeypatch.setattr(
        "api.mcp.tools.generate.resolve_dispatch",
        lambda: lambda sid, data, cost: dispatched.append((sid, cost)),
    )

    def factory(**kwargs):
        return httpx2.AsyncClient(
            transport=StreamingASGITransport(app), **kwargs
        )

    async def _flow():
        transport = StreamableHttpTransport(
            url="http://testserver/mcp",
            auth="good-token",
            httpx_client_factory=factory,
        )
        async with run_asgi_lifespan(app):
            async with Client(transport) as client:
                assert {t.name for t in await client.list_tools()} == EXPECTED_TOOLS
                me = await client.call_tool("get_me", {})
                assert '"credits":90' in me.content[0].text.replace(" ", "")
                gen = await client.call_tool(
                    "generate_reels",
                    {
                        "template_name": "basic",
                        "avatar_names": ["narrator"],
                        "amount": 2,
                        "input_text": "test topic",
                    },
                )
                assert '"series_id":1' in gen.content[0].text.replace(" ", "")
                assert '"remaining_credits":86' in gen.content[0].text.replace(" ", "")
                status = await client.call_tool("get_series_status", {"series_id": 1})
                assert "Queued" in status.content[0].text

    asyncio.run(_flow())
    assert dispatched == [(1, 4)]

    async def _bad_token():
        transport = StreamableHttpTransport(
            url="http://testserver/mcp",
            auth="bad-token",
            httpx_client_factory=factory,
        )
        async with run_asgi_lifespan(app):
            async with Client(transport) as client:
                await client.list_tools()

    with pytest.raises(Exception):
        asyncio.run(_bad_token())


# --- REST regression (refactored routers) -----------------------------------

def _override_auth_and_db(engine, uid="u1"):
    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": uid,
        "email": f"{uid}@x.com",
    }


def test_rest_public_catalog_uses_shared_service(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
    _override_auth_and_db(engine)
    try:
        response = TestClient(app).get("/api/public/video-templates")
        assert response.status_code == 200
        templates = {t["name"]: t for t in response.json()}
        assert templates["basic"]["credits"] == 2
        assert len(templates["basic"]["tags"]) > 0
        assert templates["broken"]["tags"] == []
    finally:
        app.dependency_overrides.clear()


def test_rest_series_scoped_to_caller(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        mine_id = seed_series(session, "u1").id
        seed_series(session, "u2")
    _override_auth_and_db(engine)
    try:
        client = TestClient(app)
        response = client.get("/api/series")
        assert response.status_code == 200
        assert [s["id"] for s in response.json()] == [mine_id]
        assert client.get("/api/status/9999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_rest_generate_happy_path_dispatches(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
    worker_calls = []
    # The route still dispatches through request-scoped BackgroundTasks; the
    # fake worker proves the shared function hands off correctly.
    monkeypatch.setattr(
        "api.dispatch.process_reel_task",
        lambda sid, data, cost: worker_calls.append((sid, cost)),
    )
    _override_auth_and_db(engine)
    try:
        response = TestClient(app).post(
            "/api/generate",
            json={
                "template_name": "basic",
                "avatar_names": ["narrator"],
                "amount": 1,
                "input_text": "hi",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["remaining_credits"] == 88
        assert worker_calls == [(body["series_id"], 2)]
    finally:
        app.dependency_overrides.clear()


def test_rest_generate_guards_before_dispatch(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
        session.add(
            VideoTemplate(
                name="pricey", data={"edit_template": "gameplay"}, credits=100
            )
        )
        session.commit()
    _override_auth_and_db(engine)
    try:
        client = TestClient(app)
        base = {"avatar_names": ["narrator"], "amount": 1}
        assert (
            client.post(
                "/api/generate", json={**base, "template_name": "nope"}
            ).status_code
            == 404
        )
        # 100 credits > fresh 90-credit balance: rejected before any dispatch.
        assert (
            client.post(
                "/api/generate", json={**base, "template_name": "pricey"}
            ).status_code
            == 402
        )
        assert (
            client.post(
                "/api/generate",
                json={**base, "template_name": "basic", "files": ["nope"]},
            ).status_code
            == 400
        )
    finally:
        app.dependency_overrides.clear()


def test_rest_plan_reuses_shared_orchestration(tmp_path, monkeypatch):
    from api.intent_parser import ParsedPlan

    async def fake_ingest(files, links):
        return "## sources"

    async def fake_parse(plan, catalog, source_preview=None):
        return ParsedPlan(template_name="basic", avatar_names=["narrator"])

    monkeypatch.setattr("api.plan_service.ingest_sources", fake_ingest)
    monkeypatch.setattr("api.plan_service.parse_intent", fake_parse)
    worker_calls = []
    monkeypatch.setattr(
        "api.dispatch.process_reel_task",
        lambda sid, data, cost: worker_calls.append((sid, data, cost)),
    )

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
    _override_auth_and_db(engine)
    try:
        response = TestClient(app).post(
            "/api/plan", json={"instruction": "make a reel about testing"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["remaining_credits"] == 88
        assert len(worker_calls) == 1
        _, data, cost = worker_calls[0]
        assert cost == 2
        assert "make a reel about testing" in (data["input_text"] or "")
        assert "## sources" in (data["input_text"] or "")
    finally:
        app.dependency_overrides.clear()


# --- uploads service + REST regression -----------------------------------

class _FakeS3:
    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def upload_fileobj(self, body, bucket, key):
        self.uploaded.append((bucket, key, body.read()))

    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        return f"https://r2.test/{Params['Key']}"

    def delete_object(self, Bucket=None, Key=None):
        self.deleted.append((Bucket, Key))


def _patch_r2(monkeypatch):
    fake = _FakeS3()
    monkeypatch.setattr("api.uploads._r2_client", lambda: fake)
    return fake


def test_store_uploaded_file_happy_path(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from api.uploads import MAX_UPLOAD_SIZE, store_uploaded_file

    assert MAX_UPLOAD_SIZE == 50 * 1024 * 1024
    engine = make_engine(tmp_path)
    fake = _patch_r2(monkeypatch)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        stored = _asyncio.run(
            store_uploaded_file(session, "u1", "doc.pdf", b"%PDF-1.4", "application/pdf")
        )
        assert stored.filename == "doc.pdf"
        assert stored.key.startswith("uploads/u1/")
        assert stored.key in stored.url
        assert fake.uploaded[0][2] == b"%PDF-1.4"
        assert session.get(UploadedFile, stored.id) is not None


def test_store_uploaded_file_validation(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from api.uploads import MAX_UPLOAD_SIZE, store_uploaded_file

    engine = make_engine(tmp_path)
    _patch_r2(monkeypatch)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        with pytest.raises(HTTPException) as exc:
            _asyncio.run(store_uploaded_file(session, "u1", "evil.exe", b"x", None))
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            _asyncio.run(
                store_uploaded_file(session, "u1", "big.pdf", b"x" * (MAX_UPLOAD_SIZE + 1), None)
            )
        assert exc.value.status_code == 413
        with pytest.raises(HTTPException) as exc:
            _asyncio.run(store_uploaded_file(session, "u1", "", b"x", None))
        assert exc.value.status_code == 400


def test_store_uploaded_file_converts_legacy_office(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from api.uploads import store_uploaded_file

    async def fake_convert(content, filename):
        assert filename == "old.doc"
        return b"%PDF-converted"

    monkeypatch.setattr("api.uploads.convert_office_to_pdf", fake_convert)
    engine = make_engine(tmp_path)
    fake = _patch_r2(monkeypatch)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        stored = _asyncio.run(
            store_uploaded_file(session, "u1", "old.doc", b"doc-bytes", "application/msword")
        )
        assert stored.filename == "old.pdf"
        assert stored.content_type == "application/pdf"
        assert fake.uploaded[0][2] == b"%PDF-converted"


def test_delete_user_upload(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from api.uploads import delete_user_upload, store_uploaded_file

    engine = make_engine(tmp_path)
    fake = _patch_r2(monkeypatch)
    with Session(engine) as session:
        get_or_create_user(session, "u1", None)
        get_or_create_user(session, "u2", None)
        stored = _asyncio.run(
            store_uploaded_file(session, "u1", "a.pdf", b"%PDF", "application/pdf")
        )
        with pytest.raises(HTTPException) as exc:
            _asyncio.run(delete_user_upload(session, "u2", stored.id))
        assert exc.value.status_code == 404
        _asyncio.run(delete_user_upload(session, "u1", stored.id))
        assert session.get(UploadedFile, stored.id) is None
        assert fake.deleted[0][1] == stored.key

        def _boom(**kwargs):
            raise RuntimeError("r2 down")

        fake.delete_object = _boom
        stored2 = _asyncio.run(
            store_uploaded_file(session, "u1", "b.pdf", b"%PDF", "application/pdf")
        )
        with pytest.raises(HTTPException) as exc:
            _asyncio.run(delete_user_upload(session, "u1", stored2.id))
        assert exc.value.status_code == 500


def test_rest_upload_round_trip(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    _patch_r2(monkeypatch)
    _override_auth_and_db(engine)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/upload/",
            files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["filename"] == "a.pdf"
        assert client.get(f"/api/upload/{body['id']}").status_code == 200
        assert client.delete(f"/api/upload/{body['id']}").status_code == 200
        assert client.delete(f"/api/upload/{body['id']}").status_code == 404
        bad = client.post(
            "/api/upload/", files={"file": ("a.exe", b"x", "application/x")}
        )
        assert bad.status_code == 400
    finally:
        app.dependency_overrides.clear()


# --- billing service + REST regression -----------------------------------

def _seed_plans(session):
    from api.models import SubscriptionPlan

    session.add(
        SubscriptionPlan(
            stripe_price_id="price_pro",
            name="Pro",
            credits=200,
            description="Pro plan",
        )
    )
    session.commit()


def _patch_stripe(monkeypatch, calls):
    class _Customer:
        def __init__(self, id):
            self.id = id

    class _CheckoutSession:
        def __init__(self, url):
            self.url = url

    def fake_customer_create(**kwargs):
        calls.append(("customer", kwargs))
        return _Customer("cus_123")

    def fake_session_create(**kwargs):
        calls.append(("session", kwargs))
        return _CheckoutSession("https://checkout.stripe.test/s/abc")

    monkeypatch.setattr("stripe.Customer.create", fake_customer_create)
    monkeypatch.setattr("stripe.checkout.Session.create", fake_session_create)


def test_billing_checkout_service(tmp_path, monkeypatch):
    from api.billing import create_checkout_session_url, list_subscription_plans

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        _seed_plans(session)
        assert [p.stripe_price_id for p in list_subscription_plans(session)] == ["price_pro"]
        calls = []
        _patch_stripe(monkeypatch, calls)
        url = create_checkout_session_url(session, "u1", "u1@x.com", "price_pro")
        assert url.startswith("https://checkout.stripe.test/")
        kinds = [kind for kind, _ in calls]
        assert kinds == ["customer", "session"]
        assert calls[1][1]["metadata"] == {"plan_id": "price_pro"}
        # Existing customer is reused.
        calls.clear()
        create_checkout_session_url(session, "u1", "u1@x.com", "price_pro")
        assert [kind for kind, _ in calls] == ["session"]
        # Unknown price never touches Stripe.
        calls.clear()
        with pytest.raises(HTTPException) as exc:
            create_checkout_session_url(session, "u1", "u1@x.com", "price_nope")
        assert exc.value.status_code == 400
        assert calls == []


def test_rest_checkout_route_uses_service(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        _seed_plans(session)
    _patch_stripe(monkeypatch, [])
    _override_auth_and_db(engine)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/users/create-checkout-session", json={"price_id": "price_pro"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["url"].startswith("https://checkout.stripe.test/")
        bad = client.post(
            "/api/users/create-checkout-session", json={"price_id": "price_nope"}
        )
        assert bad.status_code == 400
    finally:
        app.dependency_overrides.clear()


# --- MCP tool parity + scopes --------------------------------------------

def _call_tool(token_text, name, args):
    import httpx2

    from fastmcp.client.transports import StreamableHttpTransport as _Transport
    from fastmcp.utilities.asgi_transport import (
        StreamingASGITransport as _ASGI,
    )
    from fastmcp.utilities.asgi_transport import (
        run_asgi_lifespan as _lifespan,
    )

    async def _flow():
        def factory(**kwargs):
            return httpx2.AsyncClient(transport=_ASGI(app), **kwargs)

        transport = _Transport(
            url="http://testserver/mcp",
            auth=token_text,
            httpx_client_factory=factory,
        )
        async with _lifespan(app):
            async with Client(transport) as mcp_client:
                result = await mcp_client.call_tool(name, args)
                return result.content[0].text

    return asyncio.run(_flow())


def _scoped_token(monkeypatch, scopes):
    async def fake_verify(self, token):
        if token != "scoped-token":
            return None
        return AccessToken(
            token=token,
            client_id="test",
            subject="agent-uid",
            scopes=scopes,
            claims={"email": "a@x.com"},
        )

    monkeypatch.setattr(PdftoreelOAuthProvider, "verify_token", fake_verify)


def test_mcp_upload_and_delete_round_trip(tmp_path, monkeypatch):
    import base64
    import json

    import api.mcp.db as mcp_db

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        get_or_create_user(session, "agent-uid", "a@x.com")
    monkeypatch.setattr(mcp_db, "engine", engine)
    _scoped_token(monkeypatch, ["read", "write"])
    _patch_r2(monkeypatch)

    payload = base64.b64encode(b"%PDF-hello").decode()
    stored = json.loads(_call_tool("scoped-token", "upload_file", {
        "filename": "hello.pdf",
        "content_base64": payload,
    }))
    assert stored["filename"] == "hello.pdf"
    assert stored["key"].startswith("uploads/agent-uid/")

    listed = json.loads(_call_tool("scoped-token", "list_my_uploads", {}))
    assert [f["id"] for f in listed] == [stored["id"]]

    deleted = json.loads(
        _call_tool("scoped-token", "delete_my_upload", {"file_id": stored["id"]})
    )
    assert deleted == {"ok": True}
    # Empty tool results carry no content blocks; verify deletion in the DB.
    with Session(engine) as session:
        assert session.exec(select(UploadedFile)).all() == []

    with pytest.raises(Exception, match="base64"):
        _call_tool("scoped-token", "upload_file", {
            "filename": "x.pdf",
            "content_base64": "!!!not-base64!!!",
        })
    with pytest.raises(Exception, match="400"):
        _call_tool("scoped-token", "upload_file", {
            "filename": "x.exe",
            "content_base64": payload,
        })


def test_mcp_billing_tools(tmp_path, monkeypatch):
    import json

    import api.mcp.db as mcp_db

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        _seed_plans(session)
    monkeypatch.setattr(mcp_db, "engine", engine)
    _scoped_token(monkeypatch, ["read", "write"])
    _patch_stripe(monkeypatch, [])

    plans = json.loads(_call_tool("scoped-token", "list_subscription_plans", {}))
    assert plans[0]["stripe_price_id"] == "price_pro"
    checkout = json.loads(_call_tool(
        "scoped-token", "get_subscription_checkout_url", {"price_id": "price_pro"}
    ))
    assert checkout["url"].startswith("https://checkout.stripe.test/")
    with pytest.raises(Exception, match="400"):
        _call_tool(
            "scoped-token", "get_subscription_checkout_url", {"price_id": "nope"}
        )


def test_mcp_scope_enforcement(tmp_path, monkeypatch):
    import api.mcp.db as mcp_db

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)
    monkeypatch.setattr(mcp_db, "engine", engine)
    _scoped_token(monkeypatch, ["read"])

    # Reads work on a read-only connection.
    assert "basic" in _call_tool("scoped-token", "list_video_templates", {})
    # Writes are refused with a reconnect hint.
    with pytest.raises(Exception, match="Requires 'write'"):
        _call_tool("scoped-token", "generate_reels", {
            "template_name": "basic",
            "avatar_names": ["narrator"],
            "input_text": "hi",
        })
    with pytest.raises(Exception, match="Requires 'write'"):
        _call_tool("scoped-token", "delete_my_series", {"series_id": 1})
