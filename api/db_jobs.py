"""Durable generation queue for a single Basic web dyno.

The request is stored in Postgres before returning to the caller. The web
process handles one job at a time and retries interrupted work after a restart.
"""

import asyncio
import logging

from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from api.database import engine
from api.models import GenerationJob, JobStatus, ReelSeries
from api.tasks import fail_series_with_refund, process_reel_task

logger = logging.getLogger("pdftoreel.db_jobs")
MAX_ATTEMPTS = 2


def db_dispatch(series_id: int, request_data: dict, total_cost: int) -> None:
    """Persist a job; the web process polls the table for new work."""
    with Session(engine) as session:
        session.add(
            GenerationJob(
                series_id=series_id,
                request_data=request_data,
                total_cost=total_cost,
            )
        )
        session.commit()
    logger.info("Queued generation job for series %s in Postgres", series_id)


def _claim_next_job() -> tuple[int, dict, int, int] | None:
    with Session(engine) as session:
        job = session.exec(
            select(GenerationJob).order_by(GenerationJob.series_id)
        ).first()
        if job is None:
            return None
        series = session.get(ReelSeries, job.series_id)
        if series is None or series.status in (JobStatus.DONE, JobStatus.FAILED):
            session.delete(job)
            session.commit()
            return None
        job.attempts += 1
        session.add(job)
        session.commit()
        return job.series_id, job.request_data, job.total_cost, job.attempts


def _remove_if_finished(series_id: int) -> None:
    with Session(engine) as session:
        job = session.get(GenerationJob, series_id)
        series = session.get(ReelSeries, series_id)
        if job and (series is None or series.status in (JobStatus.DONE, JobStatus.FAILED)):
            session.delete(job)
            session.commit()


async def process_next_job() -> bool:
    """Run one queued job. An interrupted job remains for the next boot."""
    job = await run_in_threadpool(_claim_next_job)
    if job is None:
        return False
    series_id, request_data, total_cost, attempts = job
    if attempts > MAX_ATTEMPTS:
        logger.error("Series %s interrupted twice; failing and refunding", series_id)
        await run_in_threadpool(fail_series_with_refund, series_id, total_cost)
    else:
        logger.info("Processing Postgres job for series %s (attempt %s)", series_id, attempts)
        await process_reel_task(series_id, request_data, total_cost)
    await run_in_threadpool(_remove_if_finished, series_id)
    return True


async def run_db_worker() -> None:
    while True:
        try:
            if not await process_next_job():
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Postgres job worker error; retrying")
            await asyncio.sleep(5)
