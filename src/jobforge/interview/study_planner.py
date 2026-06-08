"""Time-boxed study planner.

Inputs: weakness topics, interview topics, and a horizon (1, 3, 7, 14 days).
Output: an ordered list of `StudyBlock`s with explicit time budgets.

Templated, not LLM — deterministic, reproducible in tests, no hallucinated
resources. The "Resources" field always says 'pick references you trust'
(same posture as `skills.plan`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import asc, select

from jobforge.applications import ApplicationError
from jobforge.db.models import InterviewPlan, InterviewStudyPlan
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.interview.study_planner")

SUPPORTED_HORIZONS = (1, 3, 7, 14)


@dataclass(frozen=True)
class StudyBlock:
    day_label: str
    focus: str
    activities: list[str]
    duration_minutes: int


@dataclass(frozen=True)
class StudyPlanDTO:
    id: int | None
    plan_id: int
    horizon_days: int
    blocks: list[StudyBlock]
    total_hours: int
    generated_at: str | None = None


# ---------------- block builders ----------------


def _technical_block(day_label: str, topic: str, minutes: int) -> StudyBlock:
    return StudyBlock(
        day_label=day_label,
        focus=topic,
        activities=[
            f"30-minute concept refresher on {topic} — official docs + one recommended tutorial.",
            f"Solve 2-3 medium practice problems related to {topic}.",
            "Write up 5-line summary of the most painful gotcha — keep for review.",
        ],
        duration_minutes=minutes,
    )


def _system_design_block(day_label: str, minutes: int) -> StudyBlock:
    return StudyBlock(
        day_label=day_label,
        focus="System design",
        activities=[
            "Pick one of: URL shortener, feed fan-out, rate limiter, leader election.",
            "Whiteboard the design end-to-end with capacity estimates.",
            "Read one industry post-mortem on a similar system and note tradeoffs.",
        ],
        duration_minutes=minutes,
    )


def _behavioral_block(day_label: str, minutes: int) -> StudyBlock:
    return StudyBlock(
        day_label=day_label,
        focus="Behavioral stories",
        activities=[
            "Draft (or refresh) 4 STAR stories — leadership, conflict, incident, ambiguity.",
            "Record yourself answering 2 of them; review for clarity and conciseness.",
            "Prepare 5 questions for the interviewer — 2 technical, 3 team/culture.",
        ],
        duration_minutes=minutes,
    )


def _company_block(day_label: str, company: str | None, minutes: int) -> StudyBlock:
    label = company or "the company"
    return StudyBlock(
        day_label=day_label,
        focus=f"Company prep: {label}",
        activities=[
            f"Read three recent posts from {label}'s engineering blog or press feed.",
            f"Draft a tight 'why {label}' answer that names one specific product or value.",
            "List 2 'great questions to ask the team' tied to the role.",
        ],
        duration_minutes=minutes,
    )


def _mock_interview_block(day_label: str, minutes: int) -> StudyBlock:
    return StudyBlock(
        day_label=day_label,
        focus="Mock interview",
        activities=[
            "Schedule one mock with a peer, mentor, or recorded self-mock.",
            "Run a 45-minute interview at real-interview pace; resist the urge to pause.",
            "Review the recording: rate yourself on clarity, structure, and pacing.",
        ],
        duration_minutes=minutes,
    )


def _review_block(day_label: str, minutes: int) -> StudyBlock:
    return StudyBlock(
        day_label=day_label,
        focus="Final review",
        activities=[
            "Re-read your STAR stories aloud.",
            "Skim every weakness topic you flagged earlier — 5 minutes each.",
            "Set out interview-day logistics (sleep, water, charger, quiet room).",
        ],
        duration_minutes=minutes,
    )


# ---------------- horizon builders ----------------


def _pick_topics(weakness_topics: list[str], interview_topics: list[str]) -> list[str]:
    """Weakness topics first (so the gap stuff hits the front of the plan)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for t in [*weakness_topics, *interview_topics]:
        kl = t.strip().lower()
        if not kl or kl in seen:
            continue
        seen.add(kl)
        ordered.append(t)
    return ordered


def _one_day(*, topics: list[str], company: str | None) -> list[StudyBlock]:
    primary = topics[0] if topics else "Core role topics"
    return [
        _technical_block("Morning", primary, 60),
        _company_block("Midday", company, 30),
        _behavioral_block("Afternoon", 45),
        _review_block("Evening", 30),
    ]


def _three_day(*, topics: list[str], company: str | None) -> list[StudyBlock]:
    blocks: list[StudyBlock] = []
    primary = topics[0] if topics else "Core role topics"
    secondary = topics[1] if len(topics) > 1 else "Algorithms + data structures"
    blocks.append(_technical_block("Day 1 — Morning", primary, 90))
    blocks.append(_behavioral_block("Day 1 — Evening", 45))
    blocks.append(_technical_block("Day 2 — Morning", secondary, 90))
    blocks.append(_system_design_block("Day 2 — Evening", 60))
    blocks.append(_mock_interview_block("Day 3 — Morning", 75))
    blocks.append(_company_block("Day 3 — Evening", company, 45))
    return blocks


def _seven_day(*, topics: list[str], company: str | None) -> list[StudyBlock]:
    blocks: list[StudyBlock] = []
    rotation = topics[:4] if topics else ["Core role topics"]
    while len(rotation) < 4:
        rotation.append("Algorithms + data structures")
    blocks.append(_technical_block("Day 1", rotation[0], 90))
    blocks.append(_technical_block("Day 2", rotation[1], 90))
    blocks.append(_system_design_block("Day 3", 90))
    blocks.append(_technical_block("Day 4", rotation[2], 75))
    blocks.append(_behavioral_block("Day 5", 60))
    blocks.append(_mock_interview_block("Day 6", 90))
    blocks.append(_company_block("Day 6 — Evening", company, 30))
    blocks.append(_review_block("Day 7", 60))
    return blocks


def _fourteen_day(*, topics: list[str], company: str | None) -> list[StudyBlock]:
    blocks: list[StudyBlock] = []
    rotation = topics[:6] if topics else ["Core role topics"]
    while len(rotation) < 6:
        rotation.append("Algorithms + data structures")
    # Week 1 — foundations + first mock
    blocks.append(_technical_block("Day 1", rotation[0], 90))
    blocks.append(_technical_block("Day 2", rotation[1], 90))
    blocks.append(_technical_block("Day 3", rotation[2], 90))
    blocks.append(_system_design_block("Day 4", 90))
    blocks.append(_behavioral_block("Day 5", 60))
    blocks.append(_mock_interview_block("Day 6", 75))
    blocks.append(_company_block("Day 7", company, 45))
    # Week 2 — depth + final mock + review
    blocks.append(_technical_block("Day 8", rotation[3], 75))
    blocks.append(_technical_block("Day 9", rotation[4], 75))
    blocks.append(_system_design_block("Day 10", 75))
    blocks.append(_technical_block("Day 11", rotation[5], 75))
    blocks.append(_behavioral_block("Day 12", 60))
    blocks.append(_mock_interview_block("Day 13", 90))
    blocks.append(_review_block("Day 14", 60))
    return blocks


def _build_blocks(
    *, horizon_days: int, topics: list[str], company: str | None
) -> list[StudyBlock]:
    if horizon_days == 1:
        return _one_day(topics=topics, company=company)
    if horizon_days == 3:
        return _three_day(topics=topics, company=company)
    if horizon_days == 7:
        return _seven_day(topics=topics, company=company)
    if horizon_days == 14:
        return _fourteen_day(topics=topics, company=company)
    raise ApplicationError(
        f"unsupported horizon {horizon_days} (allowed: {SUPPORTED_HORIZONS})"
    )


def pick_horizon_for_interview(
    *, now: datetime, interview_at: datetime | None
) -> int:
    """Choose the largest horizon that still fits before the interview.

    Falls back to 7 days when no date is known — matches the existing
    Skill Planner's default.
    """
    if interview_at is None:
        return 7
    delta = interview_at - now
    days = max(0, int(delta.total_seconds() // 86400))
    if days >= 14:
        return 14
    if days >= 7:
        return 7
    if days >= 3:
        return 3
    return 1


# ---------------- public service ----------------


async def generate_study_plan(
    plan_id: int,
    *,
    horizon_days: int,
    weakness_topics: list[str],
    interview_topics: list[str],
    company: str | None,
    persist: bool = True,
) -> StudyPlanDTO:
    if horizon_days not in SUPPORTED_HORIZONS:
        raise ApplicationError(
            f"unsupported horizon {horizon_days} (allowed: {SUPPORTED_HORIZONS})"
        )

    # Validate parent.
    async with session_scope() as session:
        parent = await session.get(InterviewPlan, plan_id)
        if parent is None:
            raise ApplicationError(f"interview plan {plan_id} not found")

    topics = _pick_topics(weakness_topics, interview_topics)
    blocks = _build_blocks(horizon_days=horizon_days, topics=topics, company=company)
    total_minutes = sum(b.duration_minutes for b in blocks)
    total_hours = round(total_minutes / 60)

    if not persist:
        return StudyPlanDTO(
            id=None,
            plan_id=plan_id,
            horizon_days=horizon_days,
            blocks=blocks,
            total_hours=total_hours,
        )

    async with session_scope() as session:
        # Replace any existing plan for this (plan_id, horizon) so we never
        # serve a stale block list for the same horizon. UniqueConstraint on
        # the table guards us, but we want a clean replace UX.
        existing = (
            await session.execute(
                select(InterviewStudyPlan)
                .where(InterviewStudyPlan.plan_id == plan_id)
                .where(InterviewStudyPlan.horizon_days == horizon_days)
            )
        ).scalar_one_or_none()
        if existing is not None:
            await session.delete(existing)
            await session.flush()

        row = InterviewStudyPlan(
            plan_id=plan_id,
            horizon_days=horizon_days,
            blocks=[asdict(b) for b in blocks],
            total_hours=total_hours,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        dto = StudyPlanDTO(
            id=row.id,
            plan_id=row.plan_id,
            horizon_days=row.horizon_days,
            blocks=blocks,
            total_hours=row.total_hours,
            generated_at=row.generated_at.isoformat() if row.generated_at else None,
        )
        session.expunge(row)

    log.info(
        "interview.study_plan.generated",
        extra={
            "plan_id": plan_id,
            "horizon_days": horizon_days,
            "blocks": len(blocks),
        },
    )
    return dto


async def list_study_plans(plan_id: int) -> list[StudyPlanDTO]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(InterviewStudyPlan)
                .where(InterviewStudyPlan.plan_id == plan_id)
                .order_by(asc(InterviewStudyPlan.horizon_days))
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)

    out: list[StudyPlanDTO] = []
    for r in rows:
        blocks = [
            StudyBlock(
                day_label=b.get("day_label", ""),
                focus=b.get("focus", ""),
                activities=list(b.get("activities") or []),
                duration_minutes=int(b.get("duration_minutes", 0)),
            )
            for b in (r.blocks or [])
        ]
        out.append(
            StudyPlanDTO(
                id=r.id,
                plan_id=r.plan_id,
                horizon_days=r.horizon_days,
                blocks=blocks,
                total_hours=r.total_hours,
                generated_at=r.generated_at.isoformat() if r.generated_at else None,
            )
        )
    return out


def study_plan_to_dict(p: StudyPlanDTO) -> dict[str, Any]:
    return {
        "id": p.id,
        "plan_id": p.plan_id,
        "horizon_days": p.horizon_days,
        "total_hours": p.total_hours,
        "blocks": [asdict(b) for b in p.blocks],
        "generated_at": p.generated_at,
    }
