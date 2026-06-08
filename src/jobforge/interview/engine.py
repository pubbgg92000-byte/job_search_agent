"""Interview preparation engine.

Generates an :class:`InterviewPlanDTO` from an application and stores it in
the `interview_plans` table. The plan structure is deterministic (driven by
`heuristics.py`) so tests can assert exact shapes without LLM mocks. The
optional :mod:`jobforge.interview.llm_augment` hook can layer LLM-generated
notes on top, but is opt-in.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import desc, select

from jobforge.applications import ApplicationError
from jobforge.company.service import CompanyIntelligenceService
from jobforge.db.models import (
    Application,
    CompanyProfile,
    DiscoveredJob,
    InterviewPlan,
    Job,
    Profile,
)
from jobforge.db.session import session_scope
from jobforge.interview.heuristics import (
    PlanInputs,
    behavioral_topics_for,
    company_specific_prep,
    confidence_score,
    estimate_difficulty,
    extract_technical_topics,
    infer_company_class,
    infer_seniority,
    select_stages,
)
from jobforge.interview.weakness import compute_weakness_report
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.interview")


# ---------------- DTOs ----------------


@dataclass(frozen=True)
class InterviewStage:
    name: str
    description: str
    typical_duration_minutes: int


@dataclass(frozen=True)
class RiskArea:
    topic: str
    reason: str
    severity: str  # one of low/medium/high


@dataclass(frozen=True)
class InterviewPlanDTO:
    id: int | None
    application_id: int
    stages: list[InterviewStage]
    technical_topics: list[str]
    behavioral_topics: list[str]
    company_prep: list[str]
    difficulty: str
    confidence_score: int
    risk_areas: list[RiskArea]
    strengths: list[str]
    notes: str | None = None
    generated_at: str | None = None
    # Convenience derived view — not stored in DB.
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)


# ---------------- data loading ----------------


async def _load_application(user_id: int, application_id: int) -> Application:
    async with session_scope() as session:
        row = await session.get(Application, application_id)
        if row is None or row.user_id != user_id:
            raise ApplicationError(f"application {application_id} not found")
        session.expunge(row)
        return row


async def _load_latest_profile(user_id: int) -> Profile | None:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            session.expunge(row)
        return row


async def _load_jd_for_application(app: Application) -> tuple[str, dict[str, Any] | None]:
    """Return (job description text, JD-side dict for matcher).

    Falls back to free-text description if there's no structured JD payload.
    """
    description = ""
    job_dict: dict[str, Any] | None = None

    async with session_scope() as session:
        if app.discovered_job_id is not None:
            dj = await session.get(DiscoveredJob, app.discovered_job_id)
            if dj is not None:
                description = dj.description or ""
                job_dict = {
                    "title": dj.title,
                    "company": dj.company,
                    "description": description,
                    "remote": dj.remote,
                    "location": dj.location,
                }
        if not description and app.job_id is not None:
            j = await session.get(Job, app.job_id)
            if j is not None:
                description = j.raw_jd_text or ""
                job_dict = {
                    "title": j.title,
                    "company": j.company,
                    "description": description,
                }
    return description, job_dict


async def _load_company_profile(company: str | None) -> CompanyProfile | None:
    if not company:
        return None
    async with session_scope() as session:
        row = (
            await session.execute(
                select(CompanyProfile).where(CompanyProfile.name == company)
            )
        ).scalar_one_or_none()
        if row is not None:
            session.expunge(row)
        return row


# ---------------- generation ----------------


async def _build_plan(
    user_id: int,
    application_id: int,
    *,
    company_service: CompanyIntelligenceService | None = None,
) -> tuple[InterviewPlanDTO, PlanInputs]:
    app = await _load_application(user_id, application_id)
    profile = await _load_latest_profile(user_id)
    jd_text, job_dict = await _load_jd_for_application(app)

    company_row = await _load_company_profile(app.company)
    company_dict: dict[str, Any] | None = None
    if company_row is not None:
        company_dict = {
            "name": company_row.name,
            "industry": company_row.industry,
            "company_size": company_row.company_size,
            "summary": company_row.summary,
            "growth_score": company_row.growth_score,
            "risk_score": company_row.risk_score,
            "tech_stack": (
                (company_row.raw_signals or {}).get("phase3b", {}).get("tech_stack")
                if isinstance(company_row.raw_signals, dict)
                else None
            ),
        }
    elif company_service is not None and app.company:
        # Opt-in path — caller wires this in if they want side-effect enrichment.
        snap = await company_service.get_or_enrich(app.company)
        company_dict = {
            "name": snap.name,
            "industry": snap.industry,
            "company_size": snap.company_size,
            "summary": snap.summary,
            "growth_score": snap.growth_score,
            "risk_score": snap.risk_score,
            "tech_stack": list(snap.tech_stack or ()),
        }

    weakness = compute_weakness_report(
        profile=profile.parsed_json if profile is not None else {},
        job=job_dict
        or {
            "title": app.title or "",
            "company": app.company or "",
            "description": jd_text,
        },
    )

    seniority = infer_seniority(app.title)
    company_class = infer_company_class(
        (company_dict or {}).get("company_size") if company_dict else None
    )
    has_take_home_hint = "take-home" in jd_text.lower() or "take home" in jd_text.lower()

    stage_templates = select_stages(
        seniority=seniority,
        company_class=company_class,
        has_take_home_hint=has_take_home_hint,
    )

    technical_topics = extract_technical_topics(
        jd_text=jd_text, missing_skills=weakness.missing_skills
    )
    behavioral_topics = behavioral_topics_for(seniority)
    company_prep = company_specific_prep(
        company=app.company,
        company_class=company_class,
        summary=(company_dict or {}).get("summary") if company_dict else None,
        industry=(company_dict or {}).get("industry") if company_dict else None,
        tech_stack=(company_dict or {}).get("tech_stack") if company_dict else None,
    )

    difficulty = estimate_difficulty(
        seniority=seniority,
        company_class=company_class,
        missing_skill_count=len(weakness.missing_skills),
    )
    confidence = confidence_score(
        matched_skill_count=len(weakness.matched_skills),
        missing_skill_count=len(weakness.missing_skills),
        has_company_intel=company_dict is not None and bool(company_dict.get("summary")),
    )

    risk_areas = [
        RiskArea(topic=r.topic, reason=r.reason, severity=r.severity)
        for r in weakness.risk_areas
    ]

    dto = InterviewPlanDTO(
        id=None,
        application_id=application_id,
        stages=[
            InterviewStage(
                name=s.name,
                description=s.description,
                typical_duration_minutes=s.typical_duration_minutes,
            )
            for s in stage_templates
        ],
        technical_topics=technical_topics,
        behavioral_topics=behavioral_topics,
        company_prep=company_prep,
        difficulty=difficulty,
        confidence_score=confidence,
        risk_areas=risk_areas,
        strengths=weakness.strengths,
        notes=None,
        matched_skills=weakness.matched_skills,
        missing_skills=weakness.missing_skills,
    )
    inputs = PlanInputs(
        application={
            "id": app.id,
            "company": app.company,
            "title": app.title,
            "status": app.status,
        },
        job_description=jd_text,
        profile=profile.parsed_json if profile is not None else {},
        company=company_dict,
        missing_skills=weakness.missing_skills,
        matched_skills=weakness.matched_skills,
        seniority=seniority,
        company_class=company_class,
    )
    return dto, inputs


async def generate_plan(
    user_id: int,
    application_id: int,
    *,
    persist: bool = True,
    company_service: CompanyIntelligenceService | None = None,
    llm_notes: str | None = None,
) -> InterviewPlanDTO:
    """Generate a plan. If persist=True, inserts a new `interview_plans` row.

    `llm_notes` is the only field that's allowed to come from an LLM —
    everything else is deterministic. Callers can pass the result of
    :func:`jobforge.interview.llm_augment.summarize_focus` here.
    """
    dto, _ = await _build_plan(user_id, application_id, company_service=company_service)
    if llm_notes is not None:
        dto = _with_notes(dto, llm_notes)

    if not persist:
        return dto

    async with session_scope() as session:
        row = InterviewPlan(
            application_id=application_id,
            stages=[asdict(s) for s in dto.stages],
            technical_topics=list(dto.technical_topics),
            behavioral_topics=list(dto.behavioral_topics),
            company_prep=list(dto.company_prep),
            difficulty=dto.difficulty,
            confidence_score=dto.confidence_score,
            risk_areas=[asdict(r) for r in dto.risk_areas],
            strengths=list(dto.strengths),
            notes=dto.notes,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        plan_id = row.id
        generated_at = row.generated_at.isoformat() if row.generated_at else None
        session.expunge(row)

    log.info(
        "interview.plan.generated",
        extra={
            "application_id": application_id,
            "plan_id": plan_id,
            "difficulty": dto.difficulty,
            "confidence": dto.confidence_score,
            "stages": len(dto.stages),
        },
    )
    return _with_id(dto, plan_id, generated_at)


def _with_id(dto: InterviewPlanDTO, plan_id: int, generated_at: str | None) -> InterviewPlanDTO:
    return InterviewPlanDTO(
        id=plan_id,
        application_id=dto.application_id,
        stages=dto.stages,
        technical_topics=dto.technical_topics,
        behavioral_topics=dto.behavioral_topics,
        company_prep=dto.company_prep,
        difficulty=dto.difficulty,
        confidence_score=dto.confidence_score,
        risk_areas=dto.risk_areas,
        strengths=dto.strengths,
        notes=dto.notes,
        generated_at=generated_at,
        matched_skills=dto.matched_skills,
        missing_skills=dto.missing_skills,
    )


def _with_notes(dto: InterviewPlanDTO, notes: str) -> InterviewPlanDTO:
    return InterviewPlanDTO(
        id=dto.id,
        application_id=dto.application_id,
        stages=dto.stages,
        technical_topics=dto.technical_topics,
        behavioral_topics=dto.behavioral_topics,
        company_prep=dto.company_prep,
        difficulty=dto.difficulty,
        confidence_score=dto.confidence_score,
        risk_areas=dto.risk_areas,
        strengths=dto.strengths,
        notes=notes,
        generated_at=dto.generated_at,
        matched_skills=dto.matched_skills,
        missing_skills=dto.missing_skills,
    )


# ---------------- retrieval ----------------


def _row_to_dto(row: InterviewPlan) -> InterviewPlanDTO:
    return InterviewPlanDTO(
        id=row.id,
        application_id=row.application_id,
        stages=[
            InterviewStage(
                name=s.get("name", ""),
                description=s.get("description", ""),
                typical_duration_minutes=int(s.get("typical_duration_minutes", 0)),
            )
            for s in (row.stages or [])
        ],
        technical_topics=list(row.technical_topics or []),
        behavioral_topics=list(row.behavioral_topics or []),
        company_prep=list(row.company_prep or []),
        difficulty=row.difficulty,
        confidence_score=row.confidence_score,
        risk_areas=[
            RiskArea(
                topic=r.get("topic", ""),
                reason=r.get("reason", ""),
                severity=r.get("severity", "medium"),
            )
            for r in (row.risk_areas or [])
        ],
        strengths=list(row.strengths or []),
        notes=row.notes,
        generated_at=row.generated_at.isoformat() if row.generated_at else None,
    )


async def get_plan(plan_id: int) -> InterviewPlanDTO | None:
    async with session_scope() as session:
        row = await session.get(InterviewPlan, plan_id)
        if row is None:
            return None
        session.expunge(row)
    return _row_to_dto(row)


async def list_plans_for_application(application_id: int) -> list[InterviewPlanDTO]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(InterviewPlan)
                .where(InterviewPlan.application_id == application_id)
                .order_by(desc(InterviewPlan.generated_at))
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return [_row_to_dto(r) for r in rows]


async def latest_plan_for_application(application_id: int) -> InterviewPlanDTO | None:
    plans = await list_plans_for_application(application_id)
    return plans[0] if plans else None


# ---------------- serialization ----------------


def plan_to_dict(dto: InterviewPlanDTO) -> dict[str, Any]:
    return {
        "id": dto.id,
        "application_id": dto.application_id,
        "stages": [asdict(s) for s in dto.stages],
        "technical_topics": list(dto.technical_topics),
        "behavioral_topics": list(dto.behavioral_topics),
        "company_prep": list(dto.company_prep),
        "difficulty": dto.difficulty,
        "confidence_score": dto.confidence_score,
        "risk_areas": [asdict(r) for r in dto.risk_areas],
        "strengths": list(dto.strengths),
        "notes": dto.notes,
        "generated_at": dto.generated_at,
        "matched_skills": list(dto.matched_skills),
        "missing_skills": list(dto.missing_skills),
    }
