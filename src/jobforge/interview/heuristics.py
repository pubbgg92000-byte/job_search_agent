"""Deterministic heuristics that drive interview-plan generation.

Kept LLM-free so plans are reproducible in tests and don't fabricate
company-specific stages we can't verify. The LLM hook in
`llm_augment.py` can layer additional context on top, but the spine is
always these rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------- stage templates ----------------

STAGE_RECRUITER = "Recruiter screen"
STAGE_HM_SCREEN = "Hiring manager screen"
STAGE_TECH_PHONE = "Technical phone screen"
STAGE_LIVE_CODING = "Live coding interview"
STAGE_TAKE_HOME = "Take-home assignment"
STAGE_SYSTEM_DESIGN = "System design interview"
STAGE_BEHAVIORAL = "Behavioral / values panel"
STAGE_ONSITE = "Onsite loop"
STAGE_BAR_RAISER = "Bar-raiser / cross-functional"


@dataclass(frozen=True)
class StageTemplate:
    name: str
    description: str
    typical_duration_minutes: int


_DEFAULT_STAGE_LIBRARY: dict[str, StageTemplate] = {
    STAGE_RECRUITER: StageTemplate(
        STAGE_RECRUITER,
        "30 minute fit + compensation conversation with a recruiter.",
        30,
    ),
    STAGE_HM_SCREEN: StageTemplate(
        STAGE_HM_SCREEN,
        "Conversation with the hiring manager on background, motivation, "
        "and a high-level tech discussion.",
        45,
    ),
    STAGE_TECH_PHONE: StageTemplate(
        STAGE_TECH_PHONE,
        "One technical interview over video — typically a medium algorithmic "
        "question or a focused language/runtime deep-dive.",
        60,
    ),
    STAGE_LIVE_CODING: StageTemplate(
        STAGE_LIVE_CODING,
        "Pair-programming or shared-editor round. Expect 1-2 questions with "
        "discussion of tradeoffs.",
        60,
    ),
    STAGE_TAKE_HOME: StageTemplate(
        STAGE_TAKE_HOME,
        "Short take-home (target 4-6 hours of focused work) followed by a "
        "review conversation.",
        90,
    ),
    STAGE_SYSTEM_DESIGN: StageTemplate(
        STAGE_SYSTEM_DESIGN,
        "Open-ended architecture interview — bounded context, scaling, "
        "data model, failure modes.",
        60,
    ),
    STAGE_BEHAVIORAL: StageTemplate(
        STAGE_BEHAVIORAL,
        "STAR-format behavioural panel covering leadership, conflict, and "
        "delivery anecdotes.",
        45,
    ),
    STAGE_ONSITE: StageTemplate(
        STAGE_ONSITE,
        "Onsite loop (virtual or in-person) — typically 3-5 back-to-back "
        "rounds combining coding, design, and behavioural.",
        240,
    ),
    STAGE_BAR_RAISER: StageTemplate(
        STAGE_BAR_RAISER,
        "Cross-functional / bar-raiser conversation focused on judgement, "
        "scope, and impact.",
        60,
    ),
}


def stage_library() -> dict[str, StageTemplate]:
    return dict(_DEFAULT_STAGE_LIBRARY)


# ---------------- title-driven seniority + size inference ----------------

_SENIORITY_KEYWORDS = {
    "principal": ("principal", "distinguished"),
    "staff": ("staff", "architect"),
    "senior": ("senior", "sr.", "sr "),
    "mid": ("software engineer ii", "engineer ii", "intermediate"),
    "junior": ("junior", "associate", "entry", "graduate", "jr."),
}


def infer_seniority(title: str | None) -> str:
    if not title:
        return "mid"
    t = title.lower()
    for level, needles in _SENIORITY_KEYWORDS.items():
        for n in needles:
            if n in t:
                return level
    return "mid"


_LARGE_COMPANY_SIZES = {"1001-5000", "5001-10000", "10000+"}
_MID_COMPANY_SIZES = {"201-500", "501-1000"}


def infer_company_class(company_size: str | None) -> str:
    """Return one of `bigtech`, `mid`, `startup`."""
    if company_size in _LARGE_COMPANY_SIZES:
        return "bigtech"
    if company_size in _MID_COMPANY_SIZES:
        return "mid"
    return "startup"


# ---------------- stage selection ----------------


def select_stages(
    *,
    seniority: str,
    company_class: str,
    has_take_home_hint: bool,
) -> list[StageTemplate]:
    """Build the ordered stage list for a given role+company class.

    Heuristics, not magic:
    - Every track starts with a recruiter screen + HM/tech screen.
    - bigtech adds an onsite loop with system design + behavioural panel
      (and the bar-raiser convention).
    - mid skips the bar-raiser but keeps system design once seniority
      reaches senior/staff/principal.
    - startup compresses to recruiter → HM → tech → take-home (when hinted)
      → founder/values chat.
    """
    lib = _DEFAULT_STAGE_LIBRARY
    stages: list[StageTemplate] = [lib[STAGE_RECRUITER], lib[STAGE_HM_SCREEN]]

    if company_class == "bigtech":
        stages.append(lib[STAGE_TECH_PHONE])
        stages.append(lib[STAGE_ONSITE])
        if seniority in ("senior", "staff", "principal"):
            stages.append(lib[STAGE_SYSTEM_DESIGN])
        stages.append(lib[STAGE_BEHAVIORAL])
        stages.append(lib[STAGE_BAR_RAISER])
    elif company_class == "mid":
        stages.append(lib[STAGE_TECH_PHONE])
        if has_take_home_hint:
            stages.append(lib[STAGE_TAKE_HOME])
        else:
            stages.append(lib[STAGE_LIVE_CODING])
        if seniority in ("senior", "staff", "principal"):
            stages.append(lib[STAGE_SYSTEM_DESIGN])
        stages.append(lib[STAGE_BEHAVIORAL])
    else:  # startup
        stages.append(lib[STAGE_TECH_PHONE])
        if has_take_home_hint:
            stages.append(lib[STAGE_TAKE_HOME])
        else:
            stages.append(lib[STAGE_LIVE_CODING])
        if seniority in ("senior", "staff", "principal"):
            stages.append(lib[STAGE_SYSTEM_DESIGN])
        stages.append(lib[STAGE_BEHAVIORAL])

    # De-duplicate while preserving order — the list can legitimately have
    # one tech round only.
    seen: set[str] = set()
    deduped: list[StageTemplate] = []
    for s in stages:
        if s.name in seen:
            continue
        seen.add(s.name)
        deduped.append(s)
    return deduped


# ---------------- difficulty + confidence ----------------


def estimate_difficulty(
    *,
    seniority: str,
    company_class: str,
    missing_skill_count: int,
) -> str:
    """One of `easy`, `medium`, `hard`, `very_hard`.

    Inputs are coarse on purpose — we're labelling the *interview process*,
    not a single round.
    """
    score = 0
    score += {
        "junior": 0,
        "mid": 1,
        "senior": 2,
        "staff": 3,
        "principal": 4,
    }.get(seniority, 1)
    score += {"startup": 0, "mid": 1, "bigtech": 2}.get(company_class, 1)
    score += min(missing_skill_count, 4)

    if score >= 8:
        return "very_hard"
    if score >= 5:
        return "hard"
    if score >= 2:
        return "medium"
    return "easy"


def confidence_score(
    *,
    matched_skill_count: int,
    missing_skill_count: int,
    has_company_intel: bool,
) -> int:
    """0-100 confidence the candidate is ready for these interviews.

    Skill match dominates (70 pts), company intel signals a small uplift
    because tailored prep is materially easier when we know the team's
    public details.
    """
    total_skills = matched_skill_count + missing_skill_count
    # nothing to compare → flat midpoint
    skill_pts = 35 if total_skills == 0 else round(70 * matched_skill_count / total_skills)
    intel_pts = 15 if has_company_intel else 5
    # Always a 10-point baseline so we don't return 0 for blank profiles.
    return max(0, min(100, skill_pts + intel_pts + 10))


# ---------------- topic extraction ----------------

_TECH_KEYWORDS = {
    "node.js": ["node", "node.js", "nodejs"],
    "typescript": ["typescript", " ts ", "ts/", "ts,"],
    "javascript": ["javascript", " js ", "js/"],
    "postgresql": ["postgres", "postgresql"],
    "react": ["react"],
    "graphql": ["graphql"],
    "rest apis": ["rest api", "restful"],
    "system design": ["system design", "scalable", "distributed"],
    "aws": [" aws", " ec2", " s3", "lambda"],
    "docker": ["docker", "container"],
    "kubernetes": ["kubernetes", "k8s"],
    "redis": ["redis"],
    "kafka": ["kafka"],
    "python": ["python", "django", "fastapi"],
    "rust": [" rust ", "rust,"],
    "go": [" golang", " go "],
    "microservices": ["microservice"],
    "ci/cd": ["ci/cd", "continuous deployment"],
    "testing": ["pytest", "jest", "unit test"],
}


def extract_technical_topics(*, jd_text: str, missing_skills: list[str]) -> list[str]:
    """Pull a clean ordered list of topics the candidate should brush up on.

    Order: missing skills (so the candidate confronts gaps first) followed
    by detected JD keywords that didn't already make the list.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for s in missing_skills:
        key = s.strip()
        kl = key.lower()
        if not key or kl in seen:
            continue
        seen.add(kl)
        ordered.append(key)
    blob = (jd_text or "").lower()
    for canonical, needles in _TECH_KEYWORDS.items():
        if canonical in seen:
            continue
        for n in needles:
            if n in blob:
                seen.add(canonical)
                ordered.append(canonical)
                break
    return ordered


_BEHAVIORAL_DEFAULTS = [
    "Tell me about a time you led a difficult project to completion.",
    "Describe a disagreement with a peer and how you resolved it.",
    "Walk me through a production incident you owned end-to-end.",
    "How do you prioritise when everything feels urgent?",
    "Describe a time you delivered feedback that was hard to hear.",
    "Tell me about a project where you had to learn something new fast.",
]


def behavioral_topics_for(seniority: str) -> list[str]:
    """Behavioural prompts widen with seniority — leadership and ambiguity
    questions matter more the higher you go."""
    base = list(_BEHAVIORAL_DEFAULTS)
    if seniority in ("senior", "staff", "principal"):
        base.extend(
            [
                "Tell me about a system-level decision you made that others initially disagreed with.",
                "How have you scaled an engineering team or process?",
                "Describe a time you owned ambiguity end-to-end.",
            ]
        )
    return base


def company_specific_prep(
    *,
    company: str | None,
    company_class: str,
    summary: str | None,
    industry: str | None,
    tech_stack: list[str] | None,
) -> list[str]:
    items: list[str] = []
    if company:
        items.append(f"Read three recent press / engineering posts from {company}.")
        items.append(
            f"Draft a 60-second answer to 'why {company}' that names a specific product or value."
        )
    if summary:
        items.append("Re-read the cached company summary — quote one fact in your intro.")
    if industry:
        items.append(
            f"Skim a recent {industry} market piece so you can speak to industry context."
        )
    if tech_stack:
        items.append(
            "Open the company's public tech stack ("
            + ", ".join(tech_stack[:4])
            + ") and have one strong opinion per item."
        )
    if company_class == "bigtech":
        items.append("Memorize the company's leadership principles or operating values.")
    elif company_class == "startup":
        items.append("Prepare 3 questions for the founder/HM about runway, pace, and product bets.")
    if not items:
        items.append(
            "Spend 30 minutes researching the company's public posts and recent product news."
        )
    return items


# ---------------- LLM-augmentation hook (default off) ----------------


@dataclass(frozen=True)
class PlanInputs:
    application: dict[str, Any]
    job_description: str
    profile: dict[str, Any]
    company: dict[str, Any] | None
    missing_skills: list[str]
    matched_skills: list[str]
    seniority: str
    company_class: str
