from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from jobforge.agents.ats_scorer import ATSScore, score_resume
from jobforge.agents.cover_letter import write_cover_letter
from jobforge.agents.jd_analyzer import analyze_jd
from jobforge.agents.tailoring import tailor_resume
from jobforge.config import get_settings
from jobforge.db.models import Job, Profile, TailoredArtifact
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.pipeline")

TARGET_SCORE = 75


class DailyRunLimitExceeded(RuntimeError):
    """Raised when the user has already used today's MAX_RUNS_PER_DAY budget."""


@dataclass
class TailorResult:
    artifact_id: int
    profile_id: int
    job_id: int
    tailored_resume_md: str
    cover_letter_md: str
    score_before: int
    score_after: int
    missing_keywords: list[str]
    company: str | None
    title: str | None


async def _load_profile(profile_id: int) -> dict[str, Any]:
    async with session_scope() as session:
        result = await session.execute(select(Profile).where(Profile.id == profile_id))
        profile = result.scalar_one()
        return profile.parsed_json


async def _persist_job(
    *, user_id: int, jd_text: str, jd_parsed: dict[str, Any], url: str | None
) -> int:
    async with session_scope() as session:
        job = Job(
            user_id=user_id,
            source="pasted" if url is None else "url",
            url=url,
            company=jd_parsed.get("company"),
            title=jd_parsed.get("title"),
            raw_jd_text=jd_text,
            parsed_json=jd_parsed,
        )
        session.add(job)
        await session.flush()
        return job.id


async def _persist_artifact(
    *,
    user_id: int,
    job_id: int,
    profile_id: int,
    tailored_md: str,
    cover_md: str,
    final_score: ATSScore,
    model_used: str,
) -> int:
    async with session_scope() as session:
        artifact = TailoredArtifact(
            user_id=user_id,
            job_id=job_id,
            profile_id=profile_id,
            tailored_resume_md=tailored_md,
            cover_letter_md=cover_md,
            ats_score=final_score.score,
            missing_keywords=final_score.all_missing,
            model_used=model_used,
        )
        session.add(artifact)
        await session.flush()
        return artifact.id


async def _count_artifacts_in_last_24h(user_id: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    async with session_scope() as session:
        result = await session.execute(
            select(func.count(TailoredArtifact.id))
            .where(TailoredArtifact.user_id == user_id)
            .where(TailoredArtifact.created_at >= cutoff)
        )
        return int(result.scalar_one() or 0)


async def tailor_for_jd(
    *,
    profile_id: int,
    jd_text: str,
    user_id: int | None = None,
    company_name: str | None = None,
    url: str | None = None,
) -> TailorResult:
    """Run the full Phase 1 pipeline for a single (profile, JD) pair.

    1. Analyze the JD.
    2. Score the raw profile resume against the JD (baseline score).
    3. Tailor the resume with the missing-keyword hints.
    4. Re-score the tailored output.
    5. If under TARGET_SCORE, do ONE retry with the remaining missing keywords.
    6. Generate a cover letter.
    7. Persist the job + the artifact. Return everything.
    """
    settings = get_settings()
    user_id = user_id or settings.sole_user_id

    used = await _count_artifacts_in_last_24h(user_id)
    if used >= settings.max_runs_per_day:
        log.warning(
            "pipeline.rate_limited",
            extra={"user_id": user_id, "used": used, "limit": settings.max_runs_per_day},
        )
        raise DailyRunLimitExceeded(
            f"daily limit reached: {used}/{settings.max_runs_per_day} runs in the last 24h"
        )

    log.info(
        "pipeline.start",
        extra={"user_id": user_id, "profile_id": profile_id, "runs_used_24h": used},
    )

    profile = await _load_profile(profile_id)

    jd_parsed = await analyze_jd(jd_text)
    job_id = await _persist_job(
        user_id=user_id, jd_text=jd_text, jd_parsed=jd_parsed, url=url
    )
    log.info(
        "pipeline.jd_analyzed",
        extra={
            "job_id": job_id,
            "company": jd_parsed.get("company"),
            "title": jd_parsed.get("title"),
        },
    )

    profile_text = _profile_to_plain_text(profile)
    baseline_score = score_resume(profile_text, jd_parsed)
    log.info(
        "pipeline.baseline_scored",
        extra={"score": baseline_score.score, "missing": len(baseline_score.all_missing)},
    )

    tailored_md = await tailor_resume(
        profile=profile, jd=jd_parsed, missing_keywords=baseline_score.all_missing
    )
    tailored_score = score_resume(tailored_md, jd_parsed)
    retried = False

    if tailored_score.score < TARGET_SCORE and tailored_score.all_missing:
        retried = True
        tailored_md = await tailor_resume(
            profile=profile, jd=jd_parsed, missing_keywords=tailored_score.all_missing
        )
        tailored_score = score_resume(tailored_md, jd_parsed)

    log.info(
        "pipeline.tailored",
        extra={
            "score_before": baseline_score.score,
            "score_after": tailored_score.score,
            "retried": retried,
            "target": TARGET_SCORE,
        },
    )

    cover_md = await write_cover_letter(
        profile=profile, jd=jd_parsed, company_name=company_name
    )

    artifact_id = await _persist_artifact(
        user_id=user_id,
        job_id=job_id,
        profile_id=profile_id,
        tailored_md=tailored_md,
        cover_md=cover_md,
        final_score=tailored_score,
        model_used=settings.model_tailoring,
    )
    log.info("pipeline.done", extra={"artifact_id": artifact_id, "score": tailored_score.score})

    return TailorResult(
        artifact_id=artifact_id,
        profile_id=profile_id,
        job_id=job_id,
        tailored_resume_md=tailored_md,
        cover_letter_md=cover_md,
        score_before=baseline_score.score,
        score_after=tailored_score.score,
        missing_keywords=tailored_score.all_missing,
        company=jd_parsed.get("company") or company_name,
        title=jd_parsed.get("title"),
    )


def _profile_to_plain_text(profile: dict[str, Any]) -> str:
    """Flatten a parsed profile to plain text for ATS scoring of the *baseline*.

    The tailored Markdown is already plain-text-friendly; the parsed profile JSON
    needs to be denormalized so the scorer can do substring + token matching.
    """
    parts: list[str] = []
    if summary := profile.get("summary"):
        parts.append(summary)
    if skills := profile.get("skills"):
        parts.append(", ".join(skills))
    for job in profile.get("experience", []):
        parts.append(job.get("company", ""))
        parts.append(job.get("title", ""))
        parts.extend(job.get("bullets", []))
    for proj in profile.get("projects", []):
        parts.append(proj.get("name", ""))
        parts.append(proj.get("description", ""))
        parts.extend(proj.get("stack", []))
    for edu in profile.get("education", []):
        parts.append(edu.get("institution", ""))
        parts.append(edu.get("degree", ""))
    parts.extend(profile.get("certifications", []) or [])
    return "\n".join(p for p in parts if p)
