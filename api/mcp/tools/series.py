"""Series tools: inspect and manage the caller's generation jobs."""

from api.mcp.auth import current_user_token, require_scope
from api.mcp.db import session_scope
from api.mcp.errors import mcp_errors
from api.series import (
    delete_user_series as _delete_user_series,
    get_user_series as _get_user_series,
    list_user_series as _list_user_series,
)


def get_series_status(series_id: int) -> dict:
    """Return one generation job with its status and per-reel results.

    `status` is Queued, Processing, Done, or Failed. After starting a
    generation, poll this tool every 5-10 seconds until the status is Done
    (then read each reel's video URL, title, and description) or Failed.
    """
    with mcp_errors("get_series_status"):
        require_scope("read")
        token = current_user_token()
        with session_scope() as session:
            return _get_user_series(session, token["uid"], series_id).model_dump(
                mode="json"
            )


def list_my_series(offset: int = 0, limit: int = 10) -> list[dict]:
    """List the caller's generation jobs, newest first (paginated)."""
    with mcp_errors("list_my_series"):
        require_scope("read")
        token = current_user_token()
        with session_scope() as session:
            return [
                s.model_dump(mode="json")
                for s in _list_user_series(
                    session, token["uid"], offset=offset, limit=limit
                )
            ]


def delete_my_series(series_id: int) -> dict:
    """Delete one of the caller's generation jobs and its reels."""
    with mcp_errors("delete_my_series"):
        require_scope("write")
        token = current_user_token()
        with session_scope() as session:
            _delete_user_series(session, token["uid"], series_id)
            return {"ok": True}
