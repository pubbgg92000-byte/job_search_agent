"""Rules-based recommendations engine.

No LLM — every recommendation is derived from the analytics views. Each
rec carries (a) the bottom-line, (b) a short rationale citing the
underlying numbers, and (c) an optional confidence tier so the UI can
visually de-emphasise weak signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, select

from jobforge.analytics.companies import top_companies_by_interviews
from jobforge.analytics.funnel import compute_funnel
from jobforge.analytics.outreach_perf import compute_outreach_report
from jobforge.analytics.resumes import compute_resume_report
from jobforge.analytics.sources import compute_source_report
from jobforge.db.models import SkillGapSnapshot
from jobforge.db.session import session_scope


@dataclass(frozen=True)
class Recommendation:
    kind: str  # one of source/outreach/skill/company/resume
    title: str
    detail: str
    confidence: str = "medium"  # one of low/medium/high
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationsReport:
    items: list[Recommendation]


_LOW_VOLUME_THRESHOLD = 3


# ---------------- rules ----------------


def _source_recommendation(rows: list[Any]) -> Recommendation | None:
    """Top-performing application source by interview rate."""
    with_data = [r for r in rows if r.applications >= _LOW_VOLUME_THRESHOLD]
    if not with_data:
        return None
    best = max(with_data, key=lambda r: (r.interview_rate, r.applications))
    if best.interview_rate <= 0:
        return None
    return Recommendation(
        kind="source",
        title=f"Lean into {best.source}",
        detail=(
            f"Of {best.applications} applications via {best.source}, "
            f"{best.interviews} reached interviews "
            f"({round(best.interview_rate * 100)}%). Keep prioritising this source."
        ),
        confidence="high" if best.applications >= 8 else "medium",
        extra={
            "source": best.source,
            "applications": best.applications,
            "interview_rate": best.interview_rate,
        },
    )


def _outreach_recommendation(by_kind: list[Any], follow_up: Any) -> Recommendation | None:
    """Best message kind, or a nudge to use follow-ups when they help."""
    candidates = [r for r in by_kind if r.sent >= _LOW_VOLUME_THRESHOLD]
    if candidates:
        best = max(candidates, key=lambda r: (r.response_rate, r.sent))
        if best.response_rate > 0:
            return Recommendation(
                kind="outreach",
                title=f"Send more '{best.kind.replace('_', ' ')}' messages",
                detail=(
                    f"{best.kind.replace('_', ' ')} messages have a "
                    f"{round(best.response_rate * 100)}% response rate "
                    f"({best.replied}/{best.sent}). It's outperforming other kinds."
                ),
                confidence="high" if best.sent >= 8 else "medium",
                extra={"kind": best.kind, "response_rate": best.response_rate},
            )
    if (
        follow_up.campaigns_with_follow_up >= 2
        and follow_up.follow_up_lift > 0.1
    ):
        return Recommendation(
            kind="outreach",
            title="Keep using follow-ups",
            detail=(
                f"Campaigns with a follow-up reply at "
                f"{round(follow_up.reply_rate_with_follow_up * 100)}% vs "
                f"{round(follow_up.reply_rate_without_follow_up * 100)}% "
                f"without — a "
                f"+{round(follow_up.follow_up_lift * 100)}% lift."
            ),
            confidence="medium",
            extra={"follow_up_lift": follow_up.follow_up_lift},
        )
    return None


async def _skill_recommendation(user_id: int) -> Recommendation | None:
    async with session_scope() as session:
        latest = (
            await session.execute(
                select(SkillGapSnapshot)
                .where(SkillGapSnapshot.user_id == user_id)
                .order_by(desc(SkillGapSnapshot.computed_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is not None:
            session.expunge(latest)
    if latest is None:
        return None
    gaps = (latest.gaps_json or {}).get("top_gaps") or []
    if not gaps:
        return None
    top = [g for g in gaps if isinstance(g, dict)][:3]
    if not top:
        return None
    names = ", ".join(g.get("skill", "") for g in top if g.get("skill"))
    if not names:
        return None
    return Recommendation(
        kind="skill",
        title=f"Most valuable skills to learn: {names}",
        detail=(
            f"Across {latest.jobs_considered} considered jobs, these gaps "
            "show the highest interview impact. Working on them lifts your "
            "match score across the catalogue."
        ),
        confidence="high" if latest.jobs_considered >= 50 else "medium",
        extra={"skills": [g.get("skill") for g in top if g.get("skill")]},
    )


def _company_recommendation(rows: list[Any]) -> Recommendation | None:
    with_interviews = [r for r in rows if r.interviews > 0]
    if not with_interviews:
        return None
    best = max(with_interviews, key=lambda r: (r.interviews, r.offers))
    return Recommendation(
        kind="company",
        title=f"Companies producing interviews: {best.company}",
        detail=(
            f"{best.company} has produced {best.interviews} interview(s) "
            f"out of {best.applications} application(s). Look for similar "
            "companies and tailor toward this profile."
        ),
        confidence="medium" if best.applications < 3 else "high",
        extra={"company": best.company, "interviews": best.interviews},
    )


def _resume_recommendation(rows: list[Any]) -> Recommendation | None:
    candidates = [r for r in rows if r.applications >= _LOW_VOLUME_THRESHOLD]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: (r.interview_rate, r.interviews, r.offers))
    if best.interviews == 0:
        return None
    return Recommendation(
        kind="resume",
        title=f"Resume variant #{best.artifact_id} is winning",
        detail=(
            f"Artifact #{best.artifact_id} ({best.model_used}, ATS "
            f"{best.ats_score}) has {best.interviews} interview(s) from "
            f"{best.applications} application(s) — "
            f"a {round(best.interview_rate * 100)}% interview rate. "
            "Keep this variant as the baseline for similar roles."
        ),
        confidence="high" if best.applications >= 6 else "medium",
        extra={
            "artifact_id": best.artifact_id,
            "interview_rate": best.interview_rate,
        },
    )


# ---------------- entry point ----------------


async def build_recommendations(user_id: int) -> RecommendationsReport:
    funnel = await compute_funnel(user_id)
    source_report = await compute_source_report(user_id)
    outreach_report = await compute_outreach_report(user_id)
    resume_report = await compute_resume_report(user_id)
    companies = await top_companies_by_interviews(user_id, limit=10)

    items: list[Recommendation] = []

    src = _source_recommendation(source_report.rows)
    if src is not None:
        items.append(src)
    out = _outreach_recommendation(outreach_report.by_kind, outreach_report.follow_up)
    if out is not None:
        items.append(out)
    skill = await _skill_recommendation(user_id)
    if skill is not None:
        items.append(skill)
    company = _company_recommendation(companies)
    if company is not None:
        items.append(company)
    resume = _resume_recommendation(resume_report.rows)
    if resume is not None:
        items.append(resume)

    # When we have nothing useful to say, surface a "keep going" baseline
    # so the UI never renders a hard-empty box. We only do this once the
    # user actually has SOME data — empty database returns an empty list.
    if not items and funnel.stages.applications_created > 0:
        items.append(
            Recommendation(
                kind="general",
                title="Collect more data",
                detail=(
                    "Not enough activity yet to spot trends. Aim for "
                    "5-10 applications and 3-5 outreach campaigns before "
                    "re-running this report."
                ),
                confidence="low",
            )
        )

    return RecommendationsReport(items=items)


def recommendation_to_dict(r: Recommendation) -> dict[str, Any]:
    return {
        "kind": r.kind,
        "title": r.title,
        "detail": r.detail,
        "confidence": r.confidence,
        "extra": dict(r.extra),
    }


def recommendations_to_dict(r: RecommendationsReport) -> dict[str, Any]:
    return {"items": [recommendation_to_dict(x) for x in r.items], "total": len(r.items)}
