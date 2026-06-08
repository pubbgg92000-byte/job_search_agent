"""Daily digest content builder.

Stitches together: top matches, applications, interviews, offers, rejections,
skill gaps. The output is plain Markdown — the notifier escapes for Telegram's
MarkdownV2 dialect.

Kept independent of the notifier so the same digest can drive a webhook, an
email, or a CLI `jobforge digest` command later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select

from jobforge.applications import stats as application_stats
from jobforge.applications.status import (
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
)
from jobforge.db.models import (
    DiscoveredJob,
    Profile,
)
from jobforge.db.session import session_scope
from jobforge.match import match_job
from jobforge.preferences import apply_exclusions, load_preferences
from jobforge.skills import compute_gaps


@dataclass
class DigestData:
    user_id: int
    generated_at: datetime
    jobs_discovered_24h: int
    top_matches: list[dict[str, Any]] = field(default_factory=list)
    applications_total: int = 0
    applications_by_status: dict[str, int] = field(default_factory=dict)
    interviews: int = 0
    offers: int = 0
    rejections: int = 0
    skill_gaps: list[dict[str, Any]] = field(default_factory=list)


def _job_to_dict(row: DiscoveredJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "company": row.company,
        "url": row.url,
        "remote": row.remote,
        "location": row.location,
        "description": row.description,
        "posted_at": row.posted_at,
        "salary_min": row.salary_min,
        "salary_max": row.salary_max,
        "salary_currency": row.salary_currency,
    }


async def build_digest_data(
    user_id: int,
    *,
    now: datetime | None = None,
    top_n: int = 5,
    gap_n: int = 5,
    sample_size: int = 200,
) -> DigestData:
    now = now or datetime.now(UTC)
    since_24h = now - timedelta(hours=24)

    async with session_scope() as session:
        jobs_24h = int(
            (
                await session.execute(
                    select(func.count(DiscoveredJob.id)).where(
                        DiscoveredJob.first_seen_at >= since_24h
                    )
                )
            ).scalar_one()
        )
        profile = (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        sample = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(sample_size)
            )
        ).scalars().all()
        sample_dicts = [_job_to_dict(s) for s in sample]

    top_matches: list[dict[str, Any]] = []
    gaps_payload: list[dict[str, Any]] = []
    if profile is not None and sample_dicts:
        prefs_dto = await load_preferences(user_id)
        prefs = prefs_dto.to_match_preferences()
        candidates = [d for d in sample_dicts if not apply_exclusions(prefs_dto, d)]
        scored = []
        for d in candidates:
            m = match_job(profile=profile.parsed_json, job=d, prefs=prefs)
            scored.append((d, m))
        scored.sort(key=lambda pair: pair[1].score, reverse=True)
        for d, m in scored[:top_n]:
            top_matches.append(
                {
                    "id": d["id"],
                    "title": d["title"],
                    "company": d["company"],
                    "url": d["url"],
                    "score": m.score,
                }
            )
        report = compute_gaps(
            profile=profile.parsed_json, jobs=candidates, prefs=prefs, top_n=gap_n
        )
        gaps_payload = [
            {"skill": g.skill, "importance_score": g.importance_score}
            for g in report.top_gaps
        ]

    stats = await application_stats(user_id)
    return DigestData(
        user_id=user_id,
        generated_at=now,
        jobs_discovered_24h=jobs_24h,
        top_matches=top_matches,
        applications_total=stats.total,
        applications_by_status=stats.by_status,
        interviews=(
            stats.by_status.get(STATUS_INTERVIEW_SCHEDULED, 0)
            + stats.by_status.get(STATUS_INTERVIEW_COMPLETED, 0)
        ),
        offers=stats.by_status.get(STATUS_OFFER, 0) + stats.acceptances,
        rejections=stats.rejections,
        skill_gaps=gaps_payload,
    )


def render_digest_markdown(data: DigestData) -> str:
    """Plain Markdown — the Telegram notifier escapes for MarkdownV2."""
    parts: list[str] = []
    parts.append("*JobForge Daily Digest*")
    parts.append("")
    parts.append(f"Jobs discovered (24h): {data.jobs_discovered_24h}")
    if data.top_matches:
        parts.append("")
        parts.append("Top matches:")
        for m in data.top_matches:
            parts.append(f"- {m['title']} @ {m['company']} — {m['score']}/100")
    else:
        parts.append("")
        parts.append("No matches today.")
    parts.append("")
    parts.append(
        f"Applications: {data.applications_total} total, "
        f"{data.interviews} interview-stage, {data.offers} offers, "
        f"{data.rejections} rejected"
    )
    if data.skill_gaps:
        parts.append("")
        parts.append("Top skill gaps:")
        for g in data.skill_gaps:
            parts.append(f"- {g['skill']} (importance {g['importance_score']})")
    return "\n".join(parts)


def digest_to_dict(data: DigestData) -> dict[str, Any]:
    return {
        "user_id": data.user_id,
        "generated_at": data.generated_at.isoformat(),
        "jobs_discovered_24h": data.jobs_discovered_24h,
        "top_matches": data.top_matches,
        "applications_total": data.applications_total,
        "applications_by_status": data.applications_by_status,
        "interviews": data.interviews,
        "offers": data.offers,
        "rejections": data.rejections,
        "skill_gaps": data.skill_gaps,
    }
