"""Session helper for MCP tools.

Tools open short-lived sessions against the module-level ``engine``. Tests
point ``api.mcp.db.engine`` at a throwaway SQLite database instead of the
production one.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session

from api.database import engine as _default_engine

engine = _default_engine


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
