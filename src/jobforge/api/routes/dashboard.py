"""GET /dashboard — single-payload aggregator for the future frontend.

Combines: discovered-job counts, high-quality match count, application stats,
interview/offer counts, and top skill gaps. One round-trip; deterministic.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from jobforge.applications import stats as application_stats
from jobforge.applications.status import (
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
)
from jobforge.config import get_settings
from jobforge.db.models import (
    DiscoveredJob,
    JobSyncRun,
    Profile,
)
from jobforge.db.session import session_scope
from jobforge.match import match_job
from jobforge.preferences import apply_exclusions, load_preferences
from jobforge.skills import compute_gaps

router = APIRouter()

HIGH_MATCH_THRESHOLD = 75


def _job_to_dict(row: DiscoveredJob) -> dict[str, Any]:
    return {
        "title": row.title,
        "company": row.company,
        "location": row.location,
        "remote": row.remote,
        "description": row.description,
        "posted_at": row.posted_at,
        "salary_min": row.salary_min,
        "salary_max": row.salary_max,
        "salary_currency": row.salary_currency,
    }


@router.get("")
@router.get("/")
async def dashboard() -> dict[str, Any]:
    settings = get_settings()
    user_id = settings.sole_user_id

    # --- discovery counters
    async with session_scope() as session:
        jobs_found = int(
            (await session.execute(select(func.count(DiscoveredJob.id)))).scalar_one()
        )

        since_24h = datetime.now(UTC) - timedelta(hours=24)
        jobs_found_24h = int(
            (
                await session.execute(
                    select(func.count(DiscoveredJob.id)).where(
                        DiscoveredJob.first_seen_at >= since_24h
                    )
                )
            ).scalar_one()
        )

        latest_sync = (
            await session.execute(
                select(JobSyncRun).order_by(desc(JobSyncRun.started_at)).limit(1)
            )
        ).scalar_one_or_none()
        latest_sync_payload = (
            None
            if latest_sync is None
            else {
                "source": latest_sync.source,
                "status": latest_sync.status,
                "started_at": latest_sync.started_at.isoformat(),
                "finished_at": latest_sync.finished_at.isoformat()
                if latest_sync.finished_at
                else None,
                "discovered": latest_sync.discovered_count,
                "inserted": latest_sync.inserted_count,
                "updated": latest_sync.updated_count,
            }
        )

        profile = (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        sample_jobs = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(300)
            )
        ).scalars().all()
        sample_dicts = [_job_to_dict(j) for j in sample_jobs]

    high_matches = 0
    top_gaps: list[dict[str, Any]] = []
    if profile is not None and sample_jobs:
        prefs_dto = await load_preferences(user_id)
        prefs = prefs_dto.to_match_preferences()
        considered_dicts = [
            d for d in sample_dicts if not apply_exclusions(prefs_dto, d)
        ]
        for d in considered_dicts:
            m = match_job(profile=profile.parsed_json, job=d, prefs=prefs)
            if m.score >= HIGH_MATCH_THRESHOLD:
                high_matches += 1
        report = compute_gaps(
            profile=profile.parsed_json, jobs=considered_dicts, prefs=prefs, top_n=5
        )
        top_gaps = [
            {
                "skill": g.skill,
                "frequency": g.frequency,
                "importance_score": g.importance_score,
            }
            for g in report.top_gaps
        ]

    # --- application counters
    s = await application_stats(user_id)

    return {
        "jobs_found": jobs_found,
        "jobs_found_24h": jobs_found_24h,
        "high_matches": high_matches,
        "applications": s.total,
        "applications_by_status": s.by_status,
        "interviews": (
            s.by_status.get(STATUS_INTERVIEW_SCHEDULED, 0)
            + s.by_status.get(STATUS_INTERVIEW_COMPLETED, 0)
        ),
        "offers": s.by_status.get(STATUS_OFFER, 0) + s.acceptances,
        "rejections": s.rejections,
        "interview_rate": s.interview_rate,
        "offer_rate": s.offer_rate,
        "skill_gaps": top_gaps,
        "latest_sync": latest_sync_payload,
        "profile_present": profile is not None,
    }
