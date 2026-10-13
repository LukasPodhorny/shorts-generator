"""RQ worker entry points for durable generation jobs.

Runs on Heroku via the Procfile `worker:` process type
(`python -m api.worker`). The worker reuses the exact same
`process_reel_task` coroutine as in-process dispatch, so behavior is identical;
the queue only changes *where* it runs.
"""

import asyncio
import logging
import os

from rq import Worker
from sqlmodel import Session

from api.database import engine
from api.dispatch import QUEUE_NAME
from api.models import ReelSeries
from api.redis_client import redis_client
from api.tasks import fail_series_with_refund, process_reel_task

logger = logging.getLogger("pdftoreel.worker")


def run_reel_job(series_id: int, request_data: dict, total_cost: int) -> None:
    """RQ job body: run one generation to completion.

    Skips work when the series already finished, so a redelivered job
    (retry, duplicate enqueue) is harmless.
    """
    with Session(engine) as session:
        series = session.get(ReelSeries, series_id)
        status = series.status if series else None
    if status in ("Done", "Failed"):
        logger.info("Series %s already %s; skipping duplicate job", series_id, status)
        return
    asyncio.run(process_reel_task(series_id, request_data, total_cost))


def on_job_failure(job, connection, type, value, traceback) -> None:
    """RQ failure callback: refund when the worker itself dies.

    `process_reel_task` handles its own errors (marks failed, refunds) and
    returns normally; this only fires for errors outside its control: job
    timeout, worker crash, or a deploy kill mid-run.
    """
    try:
        series_id, _request_data, total_cost = job.args
    except Exception:
        logger.exception("Unparseable failed RQ job %s", getattr(job, "id", "?"))
        return
    logger.error(
        "RQ job %s failed (%s); failing series %s with refund",
        job.id,
        value,
        series_id,
    )
    fail_series_with_refund(series_id, total_cost)


def main() -> None:
    """Start the RQ worker (Procfile entry point).

    The `rq worker --url` CLI cannot pass TLS options, and Heroku's
    `rediss://` URL needs verification disabled, so the worker boots here
    with the shared TLS-aware client factory instead.
    """
    url = os.getenv("REDIS_URL")
    if not url:
        raise SystemExit("REDIS_URL is not set; cannot start RQ worker")
    worker = Worker([QUEUE_NAME], connection=redis_client(url))
    logger.info("Starting RQ worker on queue %s", QUEUE_NAME)
    worker.work()


if __name__ == "__main__":
    main()
