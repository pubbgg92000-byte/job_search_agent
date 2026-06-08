"""Interview intelligence agent endpoints (Phase 3C)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from jobforge.applications import ApplicationError
from jobforge.config import get_settings
from jobforge.db.models import (
    Application,
    DiscoveredJob,
    InterviewPlan,
    Job,
    Profile,
)
from jobforge.db.session import session_scope
from jobforge.interview import (
    generate_plan,
    generate_questions,
    generate_study_plan,
    get_plan,
    latest_plan_for_application,
    list_plans_for_application,
    list_questions,
    list_study_plans,
    pick_horizon_for_interview,
    plan_to_dict,
    question_to_dict,
    study_plan_to_dict,
)
from jobforge.interview.questions import ALL_DIFFICULTIES
from jobforge.interview.study_planner import SUPPORTED_HORIZONS
from jobforge.interview.weakness import (
    compute_weakness_report,
    weakness_report_to_dict,
)

router = APIRouter()


# ---------------- payloads ----------------


class GeneratePlanPayload(BaseModel):
    with_llm_notes: bool = False


class GenerateQuestionsPayload(BaseModel):
    technical_topics: list[str] | None = None


class GenerateStudyPlanPayload(BaseModel):
    horizon_days: int = Field(..., ge=1, le=30)
    weakness_topics: list[str] | None = None
    interview_topics: list[str] | None = None


# ---------------- helpers ----------------


async def _require_application(application_id: int) -> Application:
    settings = get_settings()
    async with session_scope() as session:
        row = await session.get(Application, application_id)
        if row is None or row.user_id != settings.sole_user_id:
            raise HTTPException(
                status_code=404, detail=f"application {application_id} not found"
            )
        session.expunge(row)
        return row


async def _require_plan(plan_id: int) -> InterviewPlan:
    async with session_scope() as session:
        row = await session.get(InterviewPlan, plan_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"interview plan {plan_id} not found"
            )
        session.expunge(row)
        return row


async def _load_jd_text(app: Application) -> str:
    async with session_scope() as session:
        if app.discovered_job_id is not None:
            dj = await session.get(DiscoveredJob, app.discovered_job_id)
            if dj is not None and dj.description:
                return dj.description
        if app.job_id is not None:
            j = await session.get(Job, app.job_id)
            if j is not None:
                return j.raw_jd_text or ""
    return ""


async def _load_latest_profile_json() -> dict[str, Any]:
    settings = get_settings()
    async with session_scope() as session:
        row = (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == settings.sole_user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return {}
        session.expunge(row)
        return row.parsed_json or {}


# ---------------- application-scoped routes ----------------


@router.post("/applications/{application_id}/interview-prep/plan")
async def generate_plan_route(
    application_id: int, payload: GeneratePlanPayload | None = None
) -> dict[str, Any]:
    settings = get_settings()
    await _require_application(application_id)
    llm_notes: str | None = None
    if payload is not None and payload.with_llm_notes:
        # Defer import so plain tests don't import the LLM module.
        from jobforge.interview.engine import _build_plan
        from jobforge.interview.llm_augment import summarize_focus

        _, inputs = await _build_plan(settings.sole_user_id, application_id)
        llm_notes = await summarize_focus(inputs)

    try:
        dto = await generate_plan(
            settings.sole_user_id, application_id, llm_notes=llm_notes
        )
    except ApplicationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan_to_dict(dto)


@router.get("/applications/{application_id}/interview-prep/plan")
async def get_latest_plan_route(application_id: int) -> dict[str, Any]:
    await _require_application(application_id)
    dto = await latest_plan_for_application(application_id)
    if dto is None:
        raise HTTPException(
            status_code=404,
            detail=f"no interview plan for application {application_id}",
        )
    return plan_to_dict(dto)


@router.get("/applications/{application_id}/interview-prep/plans")
async def list_plans_route(application_id: int) -> dict[str, Any]:
    await _require_application(application_id)
    plans = await list_plans_for_application(application_id)
    return {"items": [plan_to_dict(p) for p in plans], "total": len(plans)}


@router.get("/applications/{application_id}/interview-prep/weaknesses")
async def weaknesses_route(application_id: int) -> dict[str, Any]:
    app = await _require_application(application_id)
    profile_json = await _load_latest_profile_json()
    jd_text = await _load_jd_text(app)
    report = compute_weakness_report(
        profile=profile_json,
        job={
            "title": app.title or "",
            "company": app.company or "",
            "description": jd_text,
        },
    )
    return weakness_report_to_dict(report)


# ---------------- plan-scoped routes ----------------


@router.get("/interview-plans/{plan_id}")
async def get_plan_route(plan_id: int) -> dict[str, Any]:
    await _require_plan(plan_id)
    dto = await get_plan(plan_id)
    if dto is None:
        raise HTTPException(status_code=404, detail=f"interview plan {plan_id} not found")
    return plan_to_dict(dto)


@router.post("/interview-plans/{plan_id}/questions")
async def generate_questions_route(
    plan_id: int, payload: GenerateQuestionsPayload | None = None
) -> dict[str, Any]:
    plan_row = await _require_plan(plan_id)
    topics = (payload.technical_topics if payload else None) or list(
        plan_row.technical_topics or []
    )
    try:
        questions = await generate_questions(plan_id, technical_topics=topics)
    except ApplicationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"items": [question_to_dict(q) for q in questions], "total": len(questions)}


@router.get("/interview-plans/{plan_id}/questions")
async def list_questions_route(
    plan_id: int,
    category: str | None = None,
    difficulty: str | None = None,
) -> dict[str, Any]:
    await _require_plan(plan_id)
    if difficulty and difficulty not in ALL_DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown difficulty '{difficulty}' (allowed: {ALL_DIFFICULTIES})",
        )
    items = await list_questions(plan_id, category=category, difficulty=difficulty)
    return {"items": [question_to_dict(q) for q in items], "total": len(items)}


@router.post("/interview-plans/{plan_id}/study-plan")
async def generate_study_plan_route(
    plan_id: int, payload: GenerateStudyPlanPayload
) -> dict[str, Any]:
    plan_row = await _require_plan(plan_id)
    if payload.horizon_days not in SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported horizon {payload.horizon_days} (allowed: {SUPPORTED_HORIZONS})"
            ),
        )
    # Pull defaults from the plan row so the UI can call with just horizon.
    app = await _require_application(plan_row.application_id)
    weakness_topics = payload.weakness_topics or [
        r.get("topic")
        for r in (plan_row.risk_areas or [])
        if isinstance(r, dict) and r.get("topic")
    ]
    interview_topics = payload.interview_topics or list(plan_row.technical_topics or [])
    try:
        dto = await generate_study_plan(
            plan_id,
            horizon_days=payload.horizon_days,
            weakness_topics=weakness_topics,
            interview_topics=interview_topics,
            company=app.company,
        )
    except ApplicationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return study_plan_to_dict(dto)


@router.get("/interview-plans/{plan_id}/study-plans")
async def list_study_plans_route(plan_id: int) -> dict[str, Any]:
    await _require_plan(plan_id)
    items = await list_study_plans(plan_id)
    return {"items": [study_plan_to_dict(p) for p in items], "total": len(items)}


# ---------------- dashboard ----------------


@router.get("/interview-prep/dashboard")
async def dashboard_route(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    async with session_scope() as session:
        # Upcoming interviews — applications currently in interview_scheduled.
        upcoming_rows = (
            await session.execute(
                select(Application)
                .where(Application.user_id == settings.sole_user_id)
                .where(Application.status == "interview_scheduled")
                .order_by(desc(Application.last_updated))
                .limit(limit)
            )
        ).scalars().all()
        for r in upcoming_rows:
            session.expunge(r)
        # Recent plans across all applications.
        plan_rows = (
            await session.execute(
                select(InterviewPlan)
                .order_by(desc(InterviewPlan.generated_at))
                .limit(limit)
            )
        ).scalars().all()
        for r in plan_rows:
            session.expunge(r)

    upcoming = [
        {
            "application_id": r.id,
            "company": r.company,
            "title": r.title,
            "status": r.status,
            "last_updated": r.last_updated.isoformat() if r.last_updated else None,
        }
        for r in upcoming_rows
    ]
    recent_plans = [
        {
            "id": r.id,
            "application_id": r.application_id,
            "difficulty": r.difficulty,
            "confidence_score": r.confidence_score,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "technical_topics": list(r.technical_topics or [])[:6],
        }
        for r in plan_rows
    ]
    # Aggregate risk topics from recent plans, ranked by frequency.
    risk_count: dict[str, int] = {}
    for r in plan_rows:
        for risk in r.risk_areas or []:
            if not isinstance(risk, dict):
                continue
            topic = risk.get("topic")
            if not isinstance(topic, str) or not topic.strip():
                continue
            risk_count[topic] = risk_count.get(topic, 0) + 1
    risk_areas = sorted(
        ({"topic": t, "count": c} for t, c in risk_count.items()),
        key=lambda x: (-x["count"], x["topic"]),
    )
    recommended_topics: list[str] = []
    seen_topics: set[str] = set()
    for r in plan_rows:
        for t in r.technical_topics or []:
            tl = t.lower()
            if tl in seen_topics:
                continue
            seen_topics.add(tl)
            recommended_topics.append(t)
        if len(recommended_topics) >= 12:
            break

    return {
        "generated_at": now.isoformat(),
        "upcoming_interviews": upcoming,
        "recent_plans": recent_plans,
        "risk_areas": risk_areas[:12],
        "recommended_topics": recommended_topics[:12],
        "recommended_horizon_days": pick_horizon_for_interview(
            now=now,
            interview_at=None,
        ),
    }
