"""Choose where generation jobs run: RQ queue in prod, in-process locally.

When `REDIS_URL` is set (Heroku with the Key-Value Store add-on), jobs are
enqueued for the worker dyno and survive web restarts and deploys. Otherwise
(local dev) jobs run in-process via request `BackgroundTasks` (HTTP routes)
or an `asyncio` task (MCP tools), exactly as before.
"""

import logging
import os

from fastapi import BackgroundTasks
from redis import Redis
from rq import Queue

from api.tasks import process_reel_task

logger = logging.getLogger("pdftoreel.dispatch")

QUEUE_NAME = "shorts"
# Generations take many minutes (up to 7 reels); the RQ default (180 s)
# would kill them. Must match the worker's --job-timeout.
JOB_TIMEOUT_SECONDS = 7200


def redis_url() -> str | None:
    return os.getenv("REDIS_URL") or None


def rq_dispatch(series_id: int, request_data: dict, total_cost: int) -> None:
    """Enqueue one generation for the worker dyno. Raises when Redis is down."""
    from api.worker import on_job_failure, run_reel_job

    queue = Queue(
        QUEUE_NAME,
        connection=Redis.from_url(redis_url()),  # type: ignore[arg-type]
        default_timeout=JOB_TIMEOUT_SECONDS,
    )
    queue.enqueue(
        run_reel_job,
        series_id,
        request_data,
        total_cost,
        on_failure=on_job_failure,
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=86400,
    )
    logger.info("Enqueued generation job for series %s", series_id)


def resolve_dispatch(background_tasks: BackgroundTasks | None = None):
    """Return the `dispatch_task` callable for `create_generation`.

    Prefers the RQ queue when Redis is configured; falls back to in-process
    dispatch otherwise. The fallback differs by caller: HTTP routes have
    request-scoped `BackgroundTasks`, MCP tools do not.
    """
    if redis_url():
        return rq_dispatch
    if background_tasks is not None:
        return lambda sid, data, cost: background_tasks.add_task(
            process_reel_task, sid, data, cost
        )
    from api.mcp.dispatch import dispatch_task as mcp_asyncio_dispatch

    return mcp_asyncio_dispatch
