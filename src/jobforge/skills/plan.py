"""Templated learning plans.

Hard rule: no hallucinated course names or links. The plans describe shape
(focus areas + time budgets) and let the user fill in resources they trust.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobforge.skills.gap import GapReport, SkillGap


@dataclass(frozen=True)
class PlanStep:
    day_range: str
    focus: str
    description: str


@dataclass(frozen=True)
class LearningPlan:
    horizon: str
    target_skills: list[SkillGap]
    steps: list[PlanStep]
    notes: list[str]


def _seven_day_steps(skills: list[SkillGap]) -> list[PlanStep]:
    if not skills:
        return []
    steps: list[PlanStep] = []
    by_pos = list(enumerate(skills, start=1))
    # Day 1-2: foundations on the #1 skill.
    s1 = by_pos[0][1]
    steps.append(
        PlanStep(
            day_range="Day 1-2",
            focus=s1.skill,
            description=(
                f"Foundations for {s1.skill}. Read the official docs and the most-starred "
                f"intro tutorial, then build the canonical 'hello world' example. ~2 hours/day."
            ),
        )
    )
    if len(by_pos) > 1:
        s2 = by_pos[1][1]
        steps.append(
            PlanStep(
                day_range="Day 3-4",
                focus=s2.skill,
                description=(
                    f"Foundations for {s2.skill}. Same shape as above — docs, an intro, "
                    f"and a small end-to-end example. ~2 hours/day."
                ),
            )
        )
    if len(by_pos) > 2:
        s3 = by_pos[2][1]
        steps.append(
            PlanStep(
                day_range="Day 5-6",
                focus=s3.skill,
                description=(
                    f"Foundations for {s3.skill}. Skim docs, build a minimum viable project. "
                    f"~2 hours/day."
                ),
            )
        )
    steps.append(
        PlanStep(
            day_range="Day 7",
            focus="Integrate",
            description=(
                "Pull the three skills above into one small portfolio project. Push it to "
                "GitHub. This becomes a talking point in the next interview."
            ),
        )
    )
    return steps


def _thirty_day_steps(skills: list[SkillGap]) -> list[PlanStep]:
    if not skills:
        return []
    steps: list[PlanStep] = []
    chunks = [skills[i : i + 2] for i in range(0, min(len(skills), 8), 2)]
    week = 1
    for chunk in chunks[:4]:
        names = " + ".join(s.skill for s in chunk)
        # Heuristic: skip "and" if only one skill in chunk.
        if len(chunk) == 1:
            names = chunk[0].skill
        steps.append(
            PlanStep(
                day_range=f"Week {week}",
                focus=names,
                description=(
                    f"Deep dive on {names}. ~1 hour/day reading + 1 hour/day hands-on. "
                    f"By end of week, ship a small public project demonstrating both."
                ),
            )
        )
        week += 1
    while len(steps) < 4:
        steps.append(
            PlanStep(
                day_range=f"Week {len(steps) + 1}",
                focus="Consolidation",
                description=(
                    "Polish the projects from prior weeks, write up a README, and update "
                    "your resume to feature them."
                ),
            )
        )
    return steps


def make_seven_day_plan(report: GapReport) -> LearningPlan:
    targets = report.top_gaps[:3]
    return LearningPlan(
        horizon="7-day",
        target_skills=targets,
        steps=_seven_day_steps(targets),
        notes=[
            "Target ~14 hours total over the week.",
            "Resources intentionally not prescribed — pick references you trust.",
        ],
    )


def make_thirty_day_plan(report: GapReport) -> LearningPlan:
    targets = report.top_gaps[:8]
    return LearningPlan(
        horizon="30-day",
        target_skills=targets,
        steps=_thirty_day_steps(targets),
        notes=[
            "Target ~2 hours/day across the month.",
            "Each weekly chunk should produce one public artifact.",
            "Re-rank gaps mid-month if your saved-jobs list shifts.",
        ],
    )


def plan_to_dict(plan: LearningPlan) -> dict[str, Any]:
    return {
        "horizon": plan.horizon,
        "target_skills": [
            {"skill": s.skill, "importance_score": s.importance_score, "frequency": s.frequency}
            for s in plan.target_skills
        ],
        "steps": [
            {"day_range": s.day_range, "focus": s.focus, "description": s.description}
            for s in plan.steps
        ],
        "notes": list(plan.notes),
    }
