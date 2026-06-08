"""Deterministic match engine.

Scores a normalized job against a structured user profile and (optional)
preferences. Six axes, each 0-100, combined via the PRD weights:

  skill: 35%   seniority: 20%   location: 15%
  remote: 10%  salary: 10%      freshness: 10%

No LLM required. Match dimensions are independent so we can tune weights
without touching scoring logic.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jobforge.agents.ats_scorer import score_resume

# --- Weights ---------------------------------------------------------------

WEIGHTS = {
    "skill": 0.35,
    "seniority": 0.20,
    "location": 0.15,
    "remote": 0.10,
    "salary": 0.10,
    "freshness": 0.10,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


_SENIORITY_ORDER = ["junior", "mid", "senior", "lead", "principal"]
_SENIORITY_KEYWORDS = {
    "junior": ("junior", "associate", "entry", "graduate", "jr."),
    "mid": ("mid", "intermediate", "software engineer ii", "engineer ii"),
    "senior": ("senior", "sr.", "sr ", "iii", "iv"),
    "lead": ("lead", "tech lead", "principal engineer", "staff"),
    "principal": ("principal", "distinguished", "architect"),
}


@dataclass(frozen=True)
class MatchResult:
    score: int
    skill_match: int
    seniority_match: int
    location_match: int
    remote_match: int
    salary_match: int
    freshness: int
    missing_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UserPreferences:
    """Optional preferences for ranking. All fields default to permissive values."""

    seniority: str | None = None
    locations: tuple[str, ...] = ()
    prefers_remote: bool = True
    salary_min_required: int | None = None
    salary_currency: str | None = None


# --- Profile helpers -------------------------------------------------------


def _profile_skills(profile: Mapping[str, Any]) -> list[str]:
    return [s for s in (profile.get("skills") or []) if isinstance(s, str) and s.strip()]


def _profile_seniority(profile: Mapping[str, Any]) -> str | None:
    """Crude inference: scan latest experience title for seniority keywords."""
    titles = [
        exp.get("title", "")
        for exp in (profile.get("experience") or [])
        if isinstance(exp, dict)
    ]
    if not titles:
        return None
    blob = " ".join(titles).lower()
    for level in reversed(_SENIORITY_ORDER):  # check most-senior first
        for kw in _SENIORITY_KEYWORDS[level]:
            if kw in blob:
                return level
    return None


# --- Skill match -----------------------------------------------------------


def _score_skills(profile: Mapping[str, Any], job_skills: Iterable[str]) -> tuple[int, list[str]]:
    """Reuse the Phase 1 ATS scorer: it normalizes case + handles multi-word terms."""
    skills = list(job_skills) or []
    if not skills:
        return 100, []
    resume_text = " ".join(_profile_skills(profile))
    # Treat all job-listing skills as required from the ranker's POV (no JD pref split here).
    pseudo_jd = {"required_skills": skills, "preferred_skills": [], "keywords": []}
    ats = score_resume(resume_text, pseudo_jd)
    return ats.score, ats.missing_required


def _job_keywords(job: Mapping[str, Any]) -> list[str]:
    """Derive a skill keyword list from a discovered_job dict.

    `job` may carry an explicit `keywords` field (from JD analysis) or we fall
    back to scanning the description/title for the user's profile-side skills
    upstream — for Phase 2A we use whatever the caller passes in via
    `match_job(..., job_keywords=...)`. This keeps the ranker independent of
    the JD-analyzer LLM call until preferences are wired.
    """
    return [k for k in (job.get("keywords") or []) if isinstance(k, str) and k.strip()]


# --- Seniority match -------------------------------------------------------


def _infer_job_seniority(job: Mapping[str, Any]) -> str | None:
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    blob = f"{title} {desc[:500]}"
    for level in reversed(_SENIORITY_ORDER):
        for kw in _SENIORITY_KEYWORDS[level]:
            if kw in blob:
                return level
    return None


def _score_seniority(profile_level: str | None, job_level: str | None) -> int:
    if not profile_level or not job_level:
        return 70  # unknown → neutral-ish
    p, j = _SENIORITY_ORDER.index(profile_level), _SENIORITY_ORDER.index(job_level)
    gap = abs(p - j)
    return max(0, 100 - gap * 30)


# --- Location match --------------------------------------------------------


def _score_location(prefs: UserPreferences, job: Mapping[str, Any]) -> int:
    job_loc = (job.get("location") or "").lower()
    if not prefs.locations:
        return 100  # no preference → full credit
    if not job_loc:
        return 60
    for wanted in prefs.locations:
        if wanted.lower() in job_loc or job_loc in wanted.lower():
            return 100
    return 30


# --- Remote match ----------------------------------------------------------


def _score_remote(prefs: UserPreferences, job: Mapping[str, Any]) -> int:
    job_remote = bool(job.get("remote"))
    if prefs.prefers_remote:
        return 100 if job_remote else 40
    return 60 if job_remote else 100  # in-office preference; remote OK but not preferred


# --- Salary match ----------------------------------------------------------


def _score_salary(prefs: UserPreferences, job: Mapping[str, Any]) -> int:
    smin = job.get("salary_min")
    smax = job.get("salary_max")
    if smin is None and smax is None:
        return 60  # missing salary → neutral
    if prefs.salary_min_required is None:
        return 100
    top = smax or smin
    if top is None:
        return 60
    if top >= prefs.salary_min_required:
        return 100
    # Linear partial credit between 50% and 100% of required.
    ratio = max(0.0, top / prefs.salary_min_required)
    return max(0, min(100, int(ratio * 100)))


# --- Freshness -------------------------------------------------------------


def _score_freshness(job: Mapping[str, Any], now: datetime | None = None) -> int:
    posted_at = job.get("posted_at")
    if not isinstance(posted_at, datetime):
        return 50
    now = now or datetime.now(UTC)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    days = max(0.0, (now - posted_at).total_seconds() / 86400.0)
    if days <= 1:
        return 100
    if days <= 7:
        return 85
    if days <= 14:
        return 70
    if days <= 30:
        return 50
    if days <= 60:
        return 25
    return 10


# --- Public entrypoint -----------------------------------------------------


def match_job(
    *,
    profile: Mapping[str, Any],
    job: Mapping[str, Any],
    prefs: UserPreferences | None = None,
    job_keywords: Iterable[str] | None = None,
    now: datetime | None = None,
) -> MatchResult:
    """Score one (profile, job) pair across all six dimensions.

    `job_keywords` is the canonical skill list to score against. If not passed,
    we derive a coarse list from the job description via a simple capitalized-
    token heuristic — works for tech jobs where stacks are name-cased.
    """
    prefs = prefs or UserPreferences()
    skills = list(job_keywords) if job_keywords is not None else _derive_keywords(job)
    skill_score, missing = _score_skills(profile, skills)

    profile_level = _profile_seniority(profile)
    job_level = _infer_job_seniority(job)
    seniority_score = _score_seniority(profile_level, job_level)

    location_score = _score_location(prefs, job)
    remote_score = _score_remote(prefs, job)
    salary_score = _score_salary(prefs, job)
    freshness_score = _score_freshness(job, now=now)

    final = round(
        skill_score * WEIGHTS["skill"]
        + seniority_score * WEIGHTS["seniority"]
        + location_score * WEIGHTS["location"]
        + remote_score * WEIGHTS["remote"]
        + salary_score * WEIGHTS["salary"]
        + freshness_score * WEIGHTS["freshness"]
    )

    return MatchResult(
        score=int(final),
        skill_match=int(skill_score),
        seniority_match=int(seniority_score),
        location_match=int(location_score),
        remote_match=int(remote_score),
        salary_match=int(salary_score),
        freshness=int(freshness_score),
        missing_skills=missing,
    )


_KEYWORD_TOKEN_RE = re.compile(r"\b([A-Z][A-Za-z0-9+#.]{1,}(?:\.[A-Za-z0-9]+)*)\b")
_NOISE_TOKENS = {
    "We", "You", "The", "Our", "And", "For", "With", "About", "If", "Apply",
    "Job", "Role", "Team", "Company", "I", "A", "An",
    "Senior", "Junior", "Lead", "Staff", "Principal", "Mid", "Engineer",
    "Developer", "Software", "Manager", "Designer", "N", "Full", "Time",
}


def _derive_keywords(job: Mapping[str, Any]) -> list[str]:
    """Crude title+description scan for capitalized name-like tokens (Python, Node.js, SvelteKit, AWS).

    Used only when the caller doesn't supply an explicit keyword list. Drops
    very common English words via a small stop-list.
    """
    title = job.get("title") or ""
    desc = (job.get("description") or "")[:2000]  # cap to keep this O(small)
    seen: set[str] = set()
    out: list[str] = []
    for blob in (title, desc):
        for match in _KEYWORD_TOKEN_RE.finditer(blob):
            token = match.group(1)
            if token in _NOISE_TOKENS:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
    return out
