"""Opt-in LLM augmentation for interview prep.

Used by the route layer when the caller passes `?with_llm_notes=true`.
Always behind a flag so the engine stays deterministic when tests run.

Tests mock the LLM call — no network is ever required.
"""
from __future__ import annotations

from jobforge.interview.heuristics import PlanInputs
from jobforge.llm.client import call_text
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.interview.llm_augment")

_SYSTEM_PROMPT = (
    "You are an interview coach. Given a structured interview prep summary, "
    "produce 3-5 punchy bullet notes the candidate should keep front-of-mind. "
    "Stay grounded — never invent company-specific facts, only emphasize the "
    "provided inputs. Output plain text, one bullet per line, prefixed with '- '."
)


def _user_prompt(inputs: PlanInputs) -> str:
    parts = [
        f"Application: {inputs.application.get('title')} at {inputs.application.get('company')}",
        f"Seniority: {inputs.seniority}",
        f"Company class: {inputs.company_class}",
        f"Missing skills: {', '.join(inputs.missing_skills) or 'none flagged'}",
        f"Matched skills: {', '.join(inputs.matched_skills) or 'none flagged'}",
    ]
    if inputs.company:
        if inputs.company.get("summary"):
            parts.append(f"Company summary: {inputs.company['summary']}")
        if inputs.company.get("tech_stack"):
            parts.append(f"Tech stack: {', '.join(inputs.company['tech_stack'][:6])}")
    if inputs.job_description:
        snippet = inputs.job_description[:1200]
        parts.append(f"JD excerpt: {snippet}")
    return "\n".join(parts)


async def summarize_focus(inputs: PlanInputs) -> str:
    """Return a short bullet list of focus areas.

    Caller decides whether to call this — the engine works fine without it.
    """
    try:
        text = await call_text(system=_SYSTEM_PROMPT, user=_user_prompt(inputs))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning(
            "interview.llm_augment.error",
            extra={"error": type(exc).__name__},
        )
        return ""
    return text.strip()
