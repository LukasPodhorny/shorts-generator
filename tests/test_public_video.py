"""Public video links require only an unguessable token, not a login."""

import asyncio
import os

_ENV_BEFORE_API_IMPORT = dict(os.environ)

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from api.database import get_session  # noqa: E402
from api.main import app  # noqa: E402
from api.models import JobStatus, Reel, ReelSeries, User  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


def test_public_video_link_only_exposes_completed_reel(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/public-video.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="owner", credits=0))
        session.add(ReelSeries(user_id="owner", status=JobStatus.DONE))
        session.commit()
        series = session.exec(select(ReelSeries)).one()
        series_id = series.id
        completed = Reel(
            series_id=series.id,
            sequence_number=1,
            status=JobStatus.DONE,
            cloudflare_r2_url="https://media.example/generated/video.mp4",
            title="Shared reel",
            description="Credits",
            local_path="/private/render.mp4",
        )
        unfinished = Reel(
            series_id=series.id,
            sequence_number=2,
            status=JobStatus.PROCESSING,
            cloudflare_r2_url="https://media.example/generated/unfinished.mp4",
        )
        session.add_all([completed, unfinished])
        session.commit()
        completed_token = completed.share_token
        unfinished_token = unfinished.share_token
        completed_id = completed.id
        assert completed_token != unfinished_token

    async def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        async def check_requests():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(f"/api/public/videos/{completed_token}")
                assert response.status_code == 200
                assert response.json() == {
                    "id": completed_id,
                    "cloudflare_r2_url": "https://media.example/generated/video.mp4",
                    "title": "Shared reel",
                    "description": "Credits",
                }
                assert (await client.get(f"/api/public/videos/{unfinished_token}")).status_code == 404
                assert (await client.get("/api/public/videos/not-a-real-token")).status_code == 404
                with Session(engine) as session:
                    session.delete(session.get(ReelSeries, series_id))
                    session.commit()
                assert (await client.get(f"/api/public/videos/{completed_token}")).status_code == 404

        asyncio.run(check_requests())
    finally:
        app.dependency_overrides.clear()
