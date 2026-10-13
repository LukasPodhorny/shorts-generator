"""Tests for durable job dispatch (api/dispatch.py, api/worker.py).

Covers backend selection (RQ vs in-process), the worker entry points, the
failure callback, and the enqueue-failure unwind in create_generation.
"""

import asyncio
import os
from types import SimpleNamespace

import pytest

_ENV_BEFORE_API_IMPORT = dict(os.environ)

from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from api.auth import get_current_user  # noqa: E402
from api.database import get_session  # noqa: E402
from api.dispatch import resolve_dispatch, rq_dispatch  # noqa: E402
from api.main import app  # noqa: E402
from api.models import (  # noqa: E402
    Avatar,
    GenerateRequest,
    GenerationConfig,
    ReelSeries,
    User,
    VideoTemplate,
)

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


def make_engine(tmp_path):
    url = f"sqlite:///{tmp_path}/dispatch.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def seed_catalog(session):
    session.add(Avatar(name="narrator", data={"instructions": "x"}))
    session.add(VideoTemplate(name="basic", data={}, credits=2))
    session.add(GenerationConfig(name="default", data={}, is_default=True))
    session.commit()


# --- backend selection --------------------------------------------------------

def test_resolve_prefers_rq_when_redis_configured(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    assert resolve_dispatch(BackgroundTasks()) is rq_dispatch
    assert resolve_dispatch() is rq_dispatch


def test_resolve_falls_back_in_process(monkeypatch):
    import api.mcp.dispatch as mcp_dispatch

    monkeypatch.delenv("REDIS_URL", raising=False)
    tasks = BackgroundTasks()
    adapter = resolve_dispatch(tasks)
    adapter(1, {"a": 1}, 2)
    assert len(tasks.tasks) == 1
    assert resolve_dispatch() is mcp_dispatch.dispatch_task


def test_rq_dispatch_enqueues_job(monkeypatch):
    import api.dispatch as dispatch_module

    enqueued = []

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, *args, **kwargs):
            enqueued.append((args, kwargs))

    monkeypatch.setattr(dispatch_module, "Queue", FakeQueue)
    monkeypatch.setattr(dispatch_module, "redis_client", lambda url: f"conn:{url}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")

    from api.worker import on_job_failure, run_reel_job

    rq_dispatch(7, {"amount": 1}, 4)
    assert len(enqueued) == 1
    args, kwargs = enqueued[0]
    assert args == (run_reel_job, 7, {"amount": 1}, 4)
    assert kwargs["on_failure"] is on_job_failure
    assert kwargs["job_timeout"] == 7200


# --- worker -------------------------------------------------------------------

def test_run_reel_job_skips_finished_series(tmp_path, monkeypatch):
    import api.worker as worker_module

    engine = make_engine(tmp_path)
    monkeypatch.setattr(worker_module, "engine", engine)
    calls = []

    async def fake_process(sid, data, cost):
        calls.append((sid, data, cost))

    monkeypatch.setattr(worker_module, "process_reel_task", fake_process)

    from api.worker import run_reel_job

    with Session(engine) as session:
        session.add(ReelSeries(id=1, user_id="u1", status="Done"))
        session.add(ReelSeries(id=2, user_id="u1", status="Queued"))
        session.commit()
    run_reel_job(1, {}, 0)
    assert calls == []
    run_reel_job(2, {"amount": 1}, 4)
    assert calls == [(2, {"amount": 1}, 4)]


def test_on_job_failure_fails_and_refunds(tmp_path, monkeypatch):
    import api.tasks as tasks_module
    import api.worker as worker_module

    engine = make_engine(tmp_path)
    monkeypatch.setattr(tasks_module, "engine", engine)
    with Session(engine) as session:
        session.add(User(id="u1", credits=86))
        session.add(ReelSeries(id=3, user_id="u1", status="Processing"))
        session.commit()

    from api.worker import on_job_failure

    job = SimpleNamespace(id="job-1", args=(3, {"amount": 1}, 4))
    on_job_failure(job, None, None, "boom", None)
    with Session(engine) as session:
        assert session.get(ReelSeries, 3).status == "Failed"
        assert session.get(User, "u1").credits == 90
    # Idempotent: a second report changes nothing.
    on_job_failure(job, None, None, "boom", None)
    with Session(engine) as session:
        assert session.get(User, "u1").credits == 90


def test_worker_main_requires_redis_url(monkeypatch):
    from api.worker import main as worker_main

    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(SystemExit, match="REDIS_URL"):
        worker_main()


def test_worker_main_boots_rq_worker(monkeypatch):
    import api.worker as worker_module

    started = {}

    class FakeWorker:
        def __init__(self, queues, connection=None):
            started["queues"] = queues
            started["connection"] = connection

        def work(self):
            started["worked"] = True

    monkeypatch.setattr(worker_module, "Worker", FakeWorker)
    monkeypatch.setattr(worker_module, "redis_client", lambda url: f"conn:{url}")
    monkeypatch.setenv("REDIS_URL", "rediss://host:6380")

    from api.worker import main as worker_main

    worker_main()
    assert started == {
        "queues": ["shorts"],
        "connection": "conn:rediss://host:6380",
        "worked": True,
    }


def test_fail_series_with_refund_never_raises(tmp_path, monkeypatch):
    import api.tasks as tasks_module

    engine = make_engine(tmp_path)
    monkeypatch.setattr(tasks_module, "engine", engine)

    from api.tasks import fail_series_with_refund

    # Missing series and missing user: still returns quietly.
    fail_series_with_refund(9999, 4)


# --- enqueue-failure unwind ----------------------------------------------------

def test_create_generation_unwinds_on_dispatch_failure(tmp_path, monkeypatch):
    import api.tasks as tasks_module
    from api.routers.generate import create_generation

    engine = make_engine(tmp_path)
    monkeypatch.setattr(tasks_module, "engine", engine)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with Session(engine) as session:
        seed_catalog(session)

        def _boom(*args):
            raise RuntimeError("redis down")

        with pytest.raises(HTTPException) as exc:
            create_generation(
                request=GenerateRequest(
                    template_name="basic", avatar_names=["narrator"]
                ),
                user_token={"uid": "u1", "email": "u1@x.com"},
                session=session,
                dispatch_task=_boom,
            )
        assert exc.value.status_code == 503
        # The unwind commits in its own session; drop cached state to see it.
        session.expire_all()
        assert session.get(User, "u1").credits == 90
        series = session.exec(select(ReelSeries)).all()
        assert len(series) == 1 and series[0].status == "Failed"


def test_rest_generate_enqueues_when_redis_set(tmp_path, monkeypatch):
    import api.dispatch as dispatch_module

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        seed_catalog(session)

    enqueued = []

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            pass

        def enqueue(self, *args, **kwargs):
            enqueued.append((args, kwargs))

    monkeypatch.setattr(dispatch_module, "Queue", FakeQueue)
    monkeypatch.setattr(dispatch_module, "redis_client", lambda url: "conn")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")

    worker_calls = []
    monkeypatch.setattr(
        "api.dispatch.process_reel_task",
        lambda *a: worker_calls.append(a),
    )

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u1",
        "email": "u1@x.com",
    }
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
        assert len(enqueued) == 1
        args, _ = enqueued[0]
        assert args[1] == response.json()["series_id"]
        assert args[3] == 2
        assert worker_calls == []  # nothing ran in-process
    finally:
        app.dependency_overrides.clear()
