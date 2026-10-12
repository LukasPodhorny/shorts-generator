"""Shared per-user series helpers used by both REST routers and the MCP server."""

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from api.models import JobStatus, ReelSeries, ReelSeriesRead


def list_user_series(
    session: Session, uid: str, offset: int = 0, limit: int = 10
) -> list[ReelSeriesRead]:
    """Return the user's series, newest first, paginated."""
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .order_by(ReelSeries.created_at.desc())  # pyright: ignore[reportAttributeAccessIssue] -- SQLAlchemy column at runtime; checker sees datetime
        .offset(offset)
        .limit(limit)
    )
    return [
        ReelSeriesRead.model_validate(s, from_attributes=True)
        for s in session.exec(statement).all()
    ]


def get_user_series(session: Session, uid: str, series_id: int) -> ReelSeriesRead:
    """Return one series the user owns, else 404 (no existence oracle)."""
    series = session.get(ReelSeries, series_id)
    if not series or series.user_id != uid:
        raise HTTPException(status_code=404, detail="Series not found")
    return ReelSeriesRead.model_validate(series, from_attributes=True)


def count_active_user_series(session: Session, uid: str) -> int:
    """Count the user's unfinished generations (Queued or Processing)."""
    statement = (
        select(func.count())
        .select_from(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .where(ReelSeries.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))
    )
    return int(session.exec(statement).one())


def delete_user_series(session: Session, uid: str, series_id: int) -> None:
    """Delete a series the user owns (cascades to reels), else 404."""
    statement = (
        select(ReelSeries)
        .where(ReelSeries.user_id == uid)
        .where(ReelSeries.id == series_id)
    )
    series_to_delete = session.exec(statement).first()
    if not series_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Series not found or you don't have permission to delete it.",
        )
    session.delete(series_to_delete)
    session.commit()
