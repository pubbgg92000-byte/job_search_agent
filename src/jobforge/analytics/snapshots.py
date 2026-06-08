"""Daily snapshot persistence for funnel trend charts.

The funnel queries are O(events) and acceptable to run on demand at
dashboard load, but trend charts ("interviews per week over the last
quarter") need history we'd have to reconstruct from events. Snapshots
let us materialise the cumulative funnel once per day and chart over
the rows directly.

`record_daily_snapshot` is idempotent — re-running on the same UTC date
updates the existing row. The intended caller is the daily scheduler
job in `jobforge.scheduler.runner`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from jobforge.analytics.funnel import compute_stages
from jobforge.db.models import AnalyticsSnapshot
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.analytics.snapshots")


@dataclass(frozen=True)
class SnapshotRow:
    id: int
    snapshot_date: str
    jobs_discovered: int
    jobs_saved: int
    applications_created: int
    applications_submitted: int
    messages_sent: int
    recruiter_replies: int
    interviews_scheduled: int
    interviews_completed: int
    offers_received: int
    offers_accepted: int
    rejections: int


def _day_bounds(now: datetime) -> datetime:
    """Truncate to midnight UTC — that's the snapshot key."""
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def record_daily_snapshot(
    user_id: int, *, now: datetime | None = None
) -> SnapshotRow:
    now = now or datetime.now(UTC)
    key = _day_bounds(now)
    stages = await compute_stages(user_id)
    async with session_scope() as session:
        existing = (
            await session.execute(
                select(AnalyticsSnapshot)
                .where(AnalyticsSnapshot.user_id == user_id)
                .where(AnalyticsSnapshot.snapshot_date == key)
            )
        ).scalar_one_or_none()
        if existing is None:
            row = AnalyticsSnapshot(
                user_id=user_id,
                snapshot_date=key,
                jobs_discovered=stages.jobs_discovered,
                jobs_saved=stages.jobs_saved,
                applications_created=stages.applications_created,
                applications_submitted=stages.applications_submitted,
                messages_sent=stages.messages_sent,
                recruiter_replies=stages.recruiter_replies,
                interviews_scheduled=stages.interviews_scheduled,
                interviews_completed=stages.interviews_completed,
                offers_received=stages.offers_received,
                offers_accepted=stages.offers_accepted,
                rejections=stages.rejections,
            )
            session.add(row)
        else:
            row = existing
            row.jobs_discovered = stages.jobs_discovered
            row.jobs_saved = stages.jobs_saved
            row.applications_created = stages.applications_created
            row.applications_submitted = stages.applications_submitted
            row.messages_sent = stages.messages_sent
            row.recruiter_replies = stages.recruiter_replies
            row.interviews_scheduled = stages.interviews_scheduled
            row.interviews_completed = stages.interviews_completed
            row.offers_received = stages.offers_received
            row.offers_accepted = stages.offers_accepted
            row.rejections = stages.rejections
        await session.flush()
        await session.refresh(row)
        snapshot_id = row.id
        session.expunge(row)
    log.info(
        "analytics.snapshot.recorded",
        extra={
            "snapshot_id": snapshot_id,
            "user_id": user_id,
            "snapshot_date": key.isoformat(),
        },
    )
    return _row_to_dto(row)


async def list_snapshots(user_id: int, *, limit: int = 30) -> list[SnapshotRow]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(AnalyticsSnapshot)
                .where(AnalyticsSnapshot.user_id == user_id)
                .order_by(desc(AnalyticsSnapshot.snapshot_date))
                .limit(limit)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return [_row_to_dto(r) for r in reversed(rows)]


def _row_to_dto(row: AnalyticsSnapshot) -> SnapshotRow:
    return SnapshotRow(
        id=row.id,
        snapshot_date=row.snapshot_date.isoformat() if row.snapshot_date else "",
        jobs_discovered=row.jobs_discovered,
        jobs_saved=row.jobs_saved,
        applications_created=row.applications_created,
        applications_submitted=row.applications_submitted,
        messages_sent=row.messages_sent,
        recruiter_replies=row.recruiter_replies,
        interviews_scheduled=row.interviews_scheduled,
        interviews_completed=row.interviews_completed,
        offers_received=row.offers_received,
        offers_accepted=row.offers_accepted,
        rejections=row.rejections,
    )


def snapshot_to_dict(s: SnapshotRow) -> dict[str, Any]:
    return {
        "id": s.id,
        "snapshot_date": s.snapshot_date,
        "jobs_discovered": s.jobs_discovered,
        "jobs_saved": s.jobs_saved,
        "applications_created": s.applications_created,
        "applications_submitted": s.applications_submitted,
        "messages_sent": s.messages_sent,
        "recruiter_replies": s.recruiter_replies,
        "interviews_scheduled": s.interviews_scheduled,
        "interviews_completed": s.interviews_completed,
        "offers_received": s.offers_received,
        "offers_accepted": s.offers_accepted,
        "rejections": s.rejections,
    }
