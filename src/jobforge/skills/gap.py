"""Skill gap engine — aggregate missing skills across the discovery catalogue.

Inputs: latest user profile + all (or top-N) discovered jobs.
For each job we run the deterministic matcher and collect `missing_skills`.

Importance score for a missing skill = sum of `match_score` for every job that's
missing it, normalized to 0-100. Skills that show up in high-ranking jobs win.

Plans are templated text (no LLM) — deterministic, no hallucination.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from jobforge.match import MatchResult, UserPreferences, match_job
from jobforge.preferences import PreferencesDTO


@dataclass(frozen=True)
class SkillGap:
    skill: str
    frequency: int
    importance_score: int
    total_match_score: int


@dataclass(frozen=True)
class GapReport:
    jobs_considered: int
    top_gaps: list[SkillGap]


def _norm(skill: str) -> str:
    return skill.strip()


def _key(skill: str) -> str:
    return skill.strip().lower()


def compute_gaps(
    *,
    profile: dict[str, Any],
    jobs: Iterable[dict[str, Any]],
    prefs: UserPreferences | None = None,
    top_n: int = 15,
) -> GapReport:
    prefs = prefs or UserPreferences()
    freq: dict[str, int] = {}
    total_score: dict[str, int] = {}
    display: dict[str, str] = {}
    considered = 0

    for job in jobs:
        considered += 1
        result: MatchResult = match_job(profile=profile, job=job, prefs=prefs)
        # Weight missing skills by this job's match score — a missing skill in a
        # 90-score job matters far more than one in a 30-score job.
        weight = max(result.score, 1)
        for skill in result.missing_skills:
            k = _key(skill)
            if not k:
                continue
            freq[k] = freq.get(k, 0) + 1
            total_score[k] = total_score.get(k, 0) + weight
            display.setdefault(k, _norm(skill))

    if not total_score:
        return GapReport(jobs_considered=considered, top_gaps=[])

    max_total = max(total_score.values())
    gaps: list[SkillGap] = []
    for k, s in total_score.items():
        gaps.append(
            SkillGap(
                skill=display[k],
                frequency=freq[k],
                importance_score=round(100 * s / max_total),
                total_match_score=s,
            )
        )
    gaps.sort(key=lambda g: (g.importance_score, g.frequency), reverse=True)
    return GapReport(jobs_considered=considered, top_gaps=gaps[:top_n])


def gap_to_dict(g: SkillGap) -> dict[str, Any]:
    return {
        "skill": g.skill,
        "frequency": g.frequency,
        "importance_score": g.importance_score,
        "total_match_score": g.total_match_score,
    }


def report_to_dict(r: GapReport) -> dict[str, Any]:
    return {
        "jobs_considered": r.jobs_considered,
        "top_gaps": [gap_to_dict(g) for g in r.top_gaps],
    }


def to_match_prefs_or_default(dto: PreferencesDTO | None) -> UserPreferences:
    return dto.to_match_preferences() if dto is not None else UserPreferences()
