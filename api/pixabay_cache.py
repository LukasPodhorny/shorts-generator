"""Durable Pixabay search cache for deployments without Redis."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


_cache = Table(
    "pixabaysearchcache",
    MetaData(),
    Column("cache_key", String(120), primary_key=True),
    Column("payload", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)


class DatabasePixabayCache:
    """Provide the get/setex interface expected by PixabayStockVideo."""

    def __init__(self, engine):
        self.engine = engine

    def get(self, key):
        with self.engine.connect() as connection:
            return connection.execute(
                select(_cache.c.payload).where(
                    _cache.c.cache_key == key,
                    _cache.c.expires_at > datetime.now(timezone.utc),
                )
            ).scalar_one_or_none()

    def setex(self, key, seconds, value):
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=seconds)
        insert = postgres_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        statement = insert(_cache).values(
            cache_key=key, payload=value, expires_at=expires_at
        ).on_conflict_do_update(
            index_elements=[_cache.c.cache_key],
            set_={"payload": value, "expires_at": expires_at},
        )
        with self.engine.begin() as connection:
            connection.execute(delete(_cache).where(_cache.c.expires_at <= now))
            connection.execute(statement)
        return True
