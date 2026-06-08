"""Career analytics API endpoints (Phase 3E)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from jobforge.analytics import (
    build_recommendations,
    company_row_to_dict,
    compute_funnel,
    compute_outreach_report,
    compute_resume_report,
    compute_source_report,
    funnel_to_dict,
    list_snapshots,
    outreach_report_to_dict,
    recommendations_to_dict,
    record_daily_snapshot,
    resume_report_to_dict,
    skill_gap_trend,
    skill_trend_point_to_dict,
    snapshot_to_dict,
    source_report_to_dict,
    top_companies_by_interviews,
)
from jobforge.config import get_settings

router = APIRouter()


@router.get("/funnel")
async def funnel_route() -> dict[str, Any]:
    settings = get_settings()
    return funnel_to_dict(await compute_funnel(settings.sole_user_id))


@router.get("/sources")
async def sources_route() -> dict[str, Any]:
    settings = get_settings()
    return source_report_to_dict(await compute_source_report(settings.sole_user_id))


@router.get("/resumes")
async def resumes_route() -> dict[str, Any]:
    settings = get_settings()
    return resume_report_to_dict(await compute_resume_report(settings.sole_user_id))


@router.get("/outreach")
async def outreach_route() -> dict[str, Any]:
    settings = get_settings()
    return outreach_report_to_dict(await compute_outreach_report(settings.sole_user_id))


@router.get("/companies")
async def companies_route(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    settings = get_settings()
    rows = await top_companies_by_interviews(settings.sole_user_id, limit=limit)
    return {"items": [company_row_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/skill-trends")
async def skill_trends_route(
    limit_points: int = Query(12, ge=1, le=60),
) -> dict[str, Any]:
    settings = get_settings()
    points = await skill_gap_trend(settings.sole_user_id, limit_points=limit_points)
    return {
        "items": [skill_trend_point_to_dict(p) for p in points],
        "total": len(points),
    }


@router.get("/recommendations")
async def recommendations_route() -> dict[str, Any]:
    settings = get_settings()
    return recommendations_to_dict(
        await build_recommendations(settings.sole_user_id)
    )


@router.get("/snapshots")
async def list_snapshots_route(
    limit: int = Query(30, ge=1, le=180),
) -> dict[str, Any]:
    settings = get_settings()
    rows = await list_snapshots(settings.sole_user_id, limit=limit)
    return {"items": [snapshot_to_dict(r) for r in rows], "total": len(rows)}


@router.post("/snapshots")
async def record_snapshot_route() -> dict[str, Any]:
    settings = get_settings()
    row = await record_daily_snapshot(settings.sole_user_id)
    return snapshot_to_dict(row)


@router.get("/dashboard")
async def analytics_dashboard_route() -> dict[str, Any]:
    """One-shot payload for the analytics page."""
    settings = get_settings()
    user_id = settings.sole_user_id
    funnel = await compute_funnel(user_id)
    sources = await compute_source_report(user_id)
    resumes = await compute_resume_report(user_id)
    outreach = await compute_outreach_report(user_id)
    companies = await top_companies_by_interviews(user_id, limit=10)
    skill_trend = await skill_gap_trend(user_id, limit_points=12)
    snapshots = await list_snapshots(user_id, limit=30)
    recs = await build_recommendations(user_id)
    return {
        "funnel": funnel_to_dict(funnel),
        "sources": source_report_to_dict(sources),
        "resumes": resume_report_to_dict(resumes),
        "outreach": outreach_report_to_dict(outreach),
        "top_companies": [company_row_to_dict(c) for c in companies],
        "skill_trend": [skill_trend_point_to_dict(p) for p in skill_trend],
        "snapshots": [snapshot_to_dict(s) for s in snapshots],
        "recommendations": recommendations_to_dict(recs),
    }
