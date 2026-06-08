"""Top-company analytics + skill-gap trend queries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, distinct, func, select

from jobforge.applications.status import (
    STATUS_ACCEPTED,
    STATUS_DECLINED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
)
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    SkillGapSnapshot,
)
from jobforge.db.session import session_scope


@dataclass(frozen=True)
class CompanyRow:
    company: str
    applications: int
    interviews: int
    offers: int


@dataclass(frozen=True)
class SkillTrendPoint:
    computed_at: str
    jobs_considered: int
    top_skills: list[dict[str, Any]]


_INTERVIEW_STATUSES = {
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_OFFER_STATUSES = {STATUS_OFFER, STATUS_ACCEPTED, STATUS_DECLINED}


async def top_companies_by_interviews(
    user_id: int, *, limit: int = 10
) -> list[CompanyRow]:
    async with session_scope() as session:
        # Applications per company.
        app_rows = (
            await session.execute(
                select(Application.company, func.count(Application.id))
                .where(Application.user_id == user_id)
                .where(Application.company.is_not(None))
                .group_by(Application.company)
            )
        ).all()
        apps_by_company: dict[str, int] = {
            str(c): int(n) for c, n in app_rows
        }

        # Interviews per company — distinct apps that ever hit an interview status.
        interview_stmt = (
            select(
                Application.company,
                func.count(distinct(ApplicationEvent.application_id)),
            )
            .select_from(ApplicationEvent)
            .join(Application, Application.id == ApplicationEvent.application_id)
            .where(Application.user_id == user_id)
            .where(Application.company.is_not(None))
            .where(ApplicationEvent.to_status.in_(_INTERVIEW_STATUSES))
            .group_by(Application.company)
        )
        interviews_by_company: dict[str, int] = {
            str(c): int(n) for c, n in (await session.execute(interview_stmt)).all()
        }

        offer_stmt = (
            select(
                Application.company,
                func.count(distinct(ApplicationEvent.application_id)),
            )
            .select_from(ApplicationEvent)
            .join(Application, Application.id == ApplicationEvent.application_id)
            .where(Application.user_id == user_id)
            .where(Application.company.is_not(None))
            .where(ApplicationEvent.to_status.in_(_OFFER_STATUSES))
            .group_by(Application.company)
        )
        offers_by_company: dict[str, int] = {
            str(c): int(n) for c, n in (await session.execute(offer_stmt)).all()
        }

    rows = [
        CompanyRow(
            company=name,
            applications=count,
            interviews=interviews_by_company.get(name, 0),
            offers=offers_by_company.get(name, 0),
        )
        for name, count in apps_by_company.items()
    ]
    rows.sort(key=lambda r: (-r.interviews, -r.offers, -r.applications, r.company))
    return rows[:limit]


async def skill_gap_trend(
    user_id: int, *, limit_points: int = 12
) -> list[SkillTrendPoint]:
    """Latest N snapshots from `skill_gap_snapshots`, oldest first."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(SkillGapSnapshot)
                .where(SkillGapSnapshot.user_id == user_id)
                .order_by(desc(SkillGapSnapshot.computed_at))
                .limit(limit_points)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    points: list[SkillTrendPoint] = []
    for r in reversed(rows):  # chronological for the chart
        gaps = (r.gaps_json or {}).get("top_gaps") or []
        clean = [
            {
                "skill": g.get("skill"),
                "importance_score": g.get("importance_score"),
                "frequency": g.get("frequency"),
            }
            for g in gaps
            if isinstance(g, dict) and g.get("skill")
        ][:8]
        points.append(
            SkillTrendPoint(
                computed_at=r.computed_at.isoformat() if r.computed_at else "",
                jobs_considered=r.jobs_considered,
                top_skills=clean,
            )
        )
    return points


def company_row_to_dict(r: CompanyRow) -> dict[str, Any]:
    return {
        "company": r.company,
        "applications": r.applications,
        "interviews": r.interviews,
        "offers": r.offers,
    }


def skill_trend_point_to_dict(p: SkillTrendPoint) -> dict[str, Any]:
    return {
        "computed_at": p.computed_at,
        "jobs_considered": p.jobs_considered,
        "top_skills": list(p.top_skills),
    }


def _utc_now() -> datetime:
    return datetime.now(UTC)
