"""Regression for stock generation after removing Redis from Heroku."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlmodel import Session, SQLModel, create_engine

from api.models import Avatar, GenerationConfig, ReelSeries, User, VideoTemplate
from api.pixabay_cache import _cache
from api.tasks import _prepare_generation_config
from aishorts.modules.stock_video.stock_video_providers import AutoStockVideo, PixabayStockVideo


def test_stock_generation_uses_database_cache_without_redis(tmp_path, monkeypatch):
    import api.tasks as tasks

    engine = create_engine(f"sqlite:///{tmp_path / 'generation.db'}")
    SQLModel.metadata.create_all(engine)
    _cache.create(engine)
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("PIXABAY_API_KEY", "test-key")

    with Session(engine) as session:
        session.add(User(id="user", credits=5))
        session.add(ReelSeries(id=1, user_id="user", status="Queued"))
        session.add(Avatar(name="narrator", data={
            "name": "narrator", "instructions": "Narrate", "lipsync_provider": "none",
            "voice": {"provider": "elevenlabs", "voice_id": "test"},
        }))
        session.add(VideoTemplate(name="stock_story", data={
            "edit_template": "stock_story", "template_config": {},
        }))
        session.add(GenerationConfig(name="production", data={}, is_default=True))
        session.commit()

    config = _prepare_generation_config(1, {
        "avatar_names": ["narrator"], "template_name": "stock_story",
    })
    provider = AutoStockVideo(**config.stock_video_config.provider_config).provider
    assert isinstance(provider, PixabayStockVideo)
    provider.cache.setex("test", 24 * 60 * 60, '{"hits": []}')
    assert provider.cache.get("test") == '{"hits": []}'

    with engine.begin() as connection:
        connection.execute(update(_cache).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        ))
    assert provider.cache.get("test") is None
