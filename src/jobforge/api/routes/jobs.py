"""Phase 2 discovery & matching API.

Endpoints:
  POST /jobs/sync                     — run all enabled source adapters
  GET  /jobs                          — paginated list w/ filters + sort
  GET  /jobs/top-matches              — top N for the SOLE_USER's latest profile
  GET  /jobs/{id}                     — one job
  GET  /jobs/{id}/match               — match details for sole user
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from jobforge.config import get_settings
from jobforge.db.models import DiscoveredJob, Profile
from jobforge.db.session import session_scope
from jobforge.discovery.service import sync_all_sources
from jobforge.match import match_job
from jobforge.preferences import apply_exclusions, load_preferences

router = APIRouter()


# --- response shapes ------------------------------------------------------


class DiscoveredJobOut(BaseModel):
    id: int
    source: str
    source_job_id: str
    company: str
    title: str
    location: str | None
    remote: bool
    url: str
    posted_at: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None

    @classmethod
    def from_row(cls, row: DiscoveredJob) -> DiscoveredJobOut:
        return cls(
            id=row.id,
            source=row.source,
            source_job_id=row.source_job_id,
            company=row.company,
            title=row.title,
            location=row.location,
            remote=row.remote,
            url=row.url,
            posted_at=row.posted_at.isoformat() if row.posted_at else None,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
        )


class DiscoveredJobDetail(DiscoveredJobOut):
    description: str
    first_seen_at: str
    last_seen_at: str

    @classmethod
    def from_row(cls, row: DiscoveredJob) -> DiscoveredJobDetail:  # type: ignore[override]
        return cls(
            id=row.id,
            source=row.source,
            source_job_id=row.source_job_id,
            company=row.company,
            title=row.title,
            location=row.location,
            remote=row.remote,
            url=row.url,
            posted_at=row.posted_at.isoformat() if row.posted_at else None,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
            description=row.description,
            first_seen_at=row.first_seen_at.isoformat(),
            last_seen_at=row.last_seen_at.isoformat(),
        )


class JobListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DiscoveredJobOut]


class SyncResponse(BaseModel):
    runs: list[dict[str, Any]]


class MatchOut(BaseModel):
    job_id: int
    profile_id: int
    score: int
    skill_match: int
    seniority_match: int
    location_match: int
    remote_match: int
    salary_match: int
    freshness: int
    missing_skills: list[str]


class TopMatchOut(BaseModel):
    job: DiscoveredJobOut
    match: MatchOut


# --- helpers --------------------------------------------------------------


SortKey = Literal["posted_at", "company", "first_seen_at"]


async def _load_latest_profile_for_sole_user() -> Profile | None:
    settings = get_settings()
    async with session_scope() as session:
        result = await session.execute(
            select(Profile)
            .where(Profile.user_id == settings.sole_user_id)
            .order_by(desc(Profile.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()


# --- endpoints ------------------------------------------------------------


@router.post("/sync")
async def sync_jobs() -> SyncResponse:
    runs = await sync_all_sources()
    return SyncResponse(
        runs=[
            {
                "source": r.source,
                "sync_run_id": r.sync_run_id,
                "status": r.status,
                "discovered": r.discovered,
                "inserted": r.inserted,
                "updated": r.updated,
                "skipped": r.skipped,
                "error": r.error,
            }
            for r in runs
        ]
    )


@router.get("")
@router.get("/")
async def list_jobs(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    company: str | None = None,
    remote: bool | None = None,
    sort: SortKey = "posted_at",
    order: Literal["asc", "desc"] = "desc",
) -> JobListResponse:
    async with session_scope() as session:
        filters = []
        if source:
            filters.append(DiscoveredJob.source == source)
        if company:
            filters.append(DiscoveredJob.company.ilike(f"%{company}%"))
        if remote is not None:
            filters.append(DiscoveredJob.remote.is_(remote))

        sort_col = {
            "posted_at": DiscoveredJob.posted_at,
            "company": DiscoveredJob.company,
            "first_seen_at": DiscoveredJob.first_seen_at,
        }[sort]
        ordering = sort_col.desc() if order == "desc" else sort_col.asc()

        total_count = int(
            (
                await session.execute(
                    select(func.count(DiscoveredJob.id)).where(*filters)
                )
            ).scalar_one()
        )

        rows = (
            await session.execute(
                select(DiscoveredJob)
                .where(*filters)
                .order_by(ordering)
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

        return JobListResponse(
            total=total_count,
            limit=limit,
            offset=offset,
            items=[DiscoveredJobOut.from_row(r) for r in rows],
        )


@router.get("/top-matches")
async def top_matches(
    limit: int = Query(10, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
) -> list[TopMatchOut]:
    profile = await _load_latest_profile_for_sole_user()
    if profile is None:
        raise HTTPException(
            status_code=404, detail="No profile yet — upload one via /profile first"
        )

    settings = get_settings()
    prefs_dto = await load_preferences(settings.sole_user_id)
    prefs = prefs_dto.to_match_preferences()
    profile_payload = profile.parsed_json

    async with session_scope() as session:
        rows = (await session.execute(select(DiscoveredJob))).scalars().all()

    scored: list[tuple[DiscoveredJob, Any]] = []
    for row in rows:
        row_dict = _row_to_dict(row)
        if apply_exclusions(prefs_dto, row_dict):
            continue
        m = match_job(profile=profile_payload, job=row_dict, prefs=prefs)
        if m.score >= min_score:
            scored.append((row, m))
    scored.sort(key=lambda pair: pair[1].score, reverse=True)

    return [
        TopMatchOut(
            job=DiscoveredJobOut.from_row(row),
            match=MatchOut(
                job_id=row.id,
                profile_id=profile.id,
                score=m.score,
                skill_match=m.skill_match,
                seniority_match=m.seniority_match,
                location_match=m.location_match,
                remote_match=m.remote_match,
                salary_match=m.salary_match,
                freshness=m.freshness,
                missing_skills=m.missing_skills,
            ),
        )
        for row, m in scored[:limit]
    ]


@router.get("/{job_id}")
async def get_job(job_id: int) -> DiscoveredJobDetail:
    async with session_scope() as session:
        row = await session.get(DiscoveredJob, job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")
        return DiscoveredJobDetail.from_row(row)


@router.get("/{job_id}/match")
async def get_match(job_id: int) -> MatchOut:
    profile = await _load_latest_profile_for_sole_user()
    if profile is None:
        raise HTTPException(
            status_code=404, detail="No profile yet — upload one via /profile first"
        )
    async with session_scope() as session:
        job_row = await session.get(DiscoveredJob, job_id)
        if job_row is None:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")

    settings = get_settings()
    prefs_dto = await load_preferences(settings.sole_user_id)
    m = match_job(
        profile=profile.parsed_json,
        job=_row_to_dict(job_row),
        prefs=prefs_dto.to_match_preferences(),
    )
    return MatchOut(
        job_id=job_row.id,
        profile_id=profile.id,
        score=m.score,
        skill_match=m.skill_match,
        seniority_match=m.seniority_match,
        location_match=m.location_match,
        remote_match=m.remote_match,
        salary_match=m.salary_match,
        freshness=m.freshness,
        missing_skills=m.missing_skills,
    )


def _row_to_dict(row: DiscoveredJob) -> dict[str, Any]:
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
