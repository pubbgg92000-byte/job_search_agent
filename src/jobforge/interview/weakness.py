"""Skill weakness analysis for interview prep.

Combines profile skills + job-required skills (extracted from the JD via the
deterministic matcher) into:

- strengths: skills the candidate has that the JD asks for
- weaknesses: skills the JD asks for but profile lacks
- risk areas: a richer view ranked by likely interview impact

Interview impact ranking is heuristic: skills the JD mentions multiple
times, or that match well-known interview-heavy keywords (system design,
algorithms, primary backend language), get higher severity.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from jobforge.match import UserPreferences, match_job


@dataclass(frozen=True)
class WeaknessRow:
    skill: str
    severity: str  # one of low/medium/high
    impact: int  # 0-100 ranking score


@dataclass(frozen=True)
class RiskAreaRow:
    topic: str
    reason: str
    severity: str


@dataclass(frozen=True)
class WeaknessReport:
    strengths: list[str]
    weaknesses: list[WeaknessRow]
    matched_skills: list[str]
    missing_skills: list[str]
    risk_areas: list[RiskAreaRow]


# Skills that, when missing, are likely to be probed in interviews and so
# should be flagged as higher-severity risk areas.
_HIGH_IMPACT_TOPICS = {
    "system design",
    "data structures",
    "algorithms",
    "scaling",
    "distributed systems",
    "concurrency",
    "node.js",
    "typescript",
    "postgresql",
    "rest apis",
    "graphql",
    "react",
    "aws",
}


def _normalize(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        cleaned = v.strip()
        kl = cleaned.lower()
        if not cleaned or kl in seen:
            continue
        seen.add(kl)
        out.append(cleaned)
    return out


def _profile_skills(profile: dict[str, Any]) -> list[str]:
    return _normalize(profile.get("skills") or [])


def _impact_for(skill: str, jd_text: str) -> int:
    """0-100 — higher means more likely to come up in interviews."""
    base = 30
    s = skill.strip().lower()
    if not s:
        return 0
    if s in _HIGH_IMPACT_TOPICS:
        base = 75
    # Mentions in the JD bump the score.
    if jd_text:
        mentions = jd_text.lower().count(s)
        base += min(mentions, 5) * 5
    return min(base, 100)


def _severity_for_impact(impact: int) -> str:
    if impact >= 70:
        return "high"
    if impact >= 45:
        return "medium"
    return "low"


def compute_weakness_report(
    *,
    profile: dict[str, Any],
    job: dict[str, Any],
    prefs: UserPreferences | None = None,
) -> WeaknessReport:
    profile = profile or {}
    profile_skills = _profile_skills(profile)
    profile_skill_set = {s.lower() for s in profile_skills}

    # Use the deterministic matcher to derive the JD's expected-skills set:
    # `missing_skills` is the part of that set the profile doesn't cover.
    match = match_job(profile=profile, job=job, prefs=prefs or UserPreferences())
    missing_skills = _normalize(match.missing_skills)
    missing_set = {s.lower() for s in missing_skills}

    # The JD's required-skill universe = matched + missing. We don't have a
    # direct accessor, so infer "matched" as profile skills that appear in
    # the JD text — close enough for the report.
    jd_text = (job.get("description") or "").lower() if isinstance(job, dict) else ""
    matched_skills = [
        s for s in profile_skills if s.lower() in jd_text and s.lower() not in missing_set
    ]
    matched_skills = _normalize(matched_skills)

    strengths = list(matched_skills)
    weaknesses_rows: list[WeaknessRow] = []
    for s in missing_skills:
        impact = _impact_for(s, jd_text)
        weaknesses_rows.append(
            WeaknessRow(skill=s, severity=_severity_for_impact(impact), impact=impact)
        )
    weaknesses_rows.sort(key=lambda r: r.impact, reverse=True)

    risk_rows: list[RiskAreaRow] = []
    for w in weaknesses_rows:
        risk_rows.append(
            RiskAreaRow(
                topic=w.skill,
                reason=(
                    f"Job description mentions {w.skill} and the profile does not."
                    if jd_text and w.skill.lower() in jd_text
                    else f"Profile is missing {w.skill}."
                ),
                severity=w.severity,
            )
        )

    # If we found zero gaps but the profile is otherwise thin, surface a
    # generic interview risk so the UI never renders an empty "Risk Areas".
    if not risk_rows and not profile_skill_set:
        risk_rows.append(
            RiskAreaRow(
                topic="Profile coverage",
                reason="No structured skills detected in the profile — interviewers will probe broadly.",
                severity="medium",
            )
        )

    return WeaknessReport(
        strengths=strengths,
        weaknesses=weaknesses_rows,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        risk_areas=risk_rows,
    )


def weakness_report_to_dict(r: WeaknessReport) -> dict[str, Any]:
    return {
        "strengths": list(r.strengths),
        "weaknesses": [
            {"skill": w.skill, "severity": w.severity, "impact": w.impact}
            for w in r.weaknesses
        ],
        "matched_skills": list(r.matched_skills),
        "missing_skills": list(r.missing_skills),
        "risk_areas": [
            {"topic": x.topic, "reason": x.reason, "severity": x.severity}
            for x in r.risk_areas
        ],
    }
