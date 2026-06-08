"""GET /skills/gaps and /skills/plan endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, select

from jobforge.config import get_settings
from jobforge.db.models import DiscoveredJob, Profile, SkillGapSnapshot
from jobforge.db.session import session_scope
from jobforge.preferences import load_preferences
from jobforge.skills import (
    compute_gaps,
    make_seven_day_plan,
    make_thirty_day_plan,
    plan_to_dict,
    report_to_dict,
)

router = APIRouter()


async def _latest_profile() -> Profile | None:
    settings = get_settings()
    async with session_scope() as session:
        return (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == settings.sole_user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()


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


async def _run_report(limit_jobs: int) -> tuple[Profile, Any]:
    profile = await _latest_profile()
    if profile is None:
        raise HTTPException(
            status_code=404, detail="No profile yet — upload one via /profile first"
        )
    settings = get_settings()
    prefs_dto = await load_preferences(settings.sole_user_id)
    prefs = prefs_dto.to_match_preferences()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(limit_jobs)
            )
        ).scalars().all()
    report = compute_gaps(
        profile=profile.parsed_json,
        jobs=(_job_to_dict(r) for r in rows),
        prefs=prefs,
    )
    return profile, report


@router.get("/gaps")
async def get_gaps(
    limit_jobs: int = Query(200, ge=1, le=2000),
    persist: bool = Query(False, description="Save snapshot for later trend analysis"),
) -> dict[str, Any]:
    settings = get_settings()
    profile, report = await _run_report(limit_jobs)
    payload = report_to_dict(report)
    if persist:
        async with session_scope() as session:
            session.add(
                SkillGapSnapshot(
                    user_id=settings.sole_user_id,
                    profile_id=profile.id,
                    jobs_considered=report.jobs_considered,
                    gaps_json=payload,
                )
            )
    return payload


@router.get("/plan")
async def get_plan(
    limit_jobs: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    _, report = await _run_report(limit_jobs)
    return {
        "report": report_to_dict(report),
        "seven_day_plan": plan_to_dict(make_seven_day_plan(report)),
        "thirty_day_plan": plan_to_dict(make_thirty_day_plan(report)),
    }
