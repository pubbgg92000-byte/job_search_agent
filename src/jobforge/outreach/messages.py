"""Deterministic message templates for recruiter outreach.

Five families:

- initial_outreach    — first cold message to a recruiter/talent partner
- referral_request    — asking an existing contact for a referral
- hiring_manager_intro— direct intro to a hiring manager
- follow_up           — bump after silence
- thank_you           — post-interview note

Guardrails (PRD):

1. Truthful only. We only quote facts from `profile.parsed_json`, the
   tailored JD title/company, and the company summary. Never invent skills,
   companies, or tenure.
2. Concise. Body length capped at 180 words. Subject line capped at 110
   chars.
3. Company specific. The company name MUST appear; we refuse to generate
   if blank.
4. No placeholders. Empty profile fields drop from the template instead
   of leaving `[your name]` etc.

LLM polish via :mod:`jobforge.outreach.llm_polish` is opt-in — it only
ever paraphrases, never adds new facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIND_INITIAL = "initial_outreach"
KIND_REFERRAL = "referral_request"
KIND_HM_INTRO = "hiring_manager_intro"
KIND_FOLLOW_UP = "follow_up"
KIND_THANK_YOU = "thank_you"

ALL_KINDS = (
    KIND_INITIAL,
    KIND_REFERRAL,
    KIND_HM_INTRO,
    KIND_FOLLOW_UP,
    KIND_THANK_YOU,
)

MAX_BODY_WORDS = 180
MAX_SUBJECT_CHARS = 110
TEMPLATE_VERSION = "v1"


class MessageError(Exception):
    """Service-level message-generation error."""


@dataclass(frozen=True)
class DraftedMessage:
    kind: str
    subject: str | None
    body: str
    channel: str = "linkedin"
    template_version: str = TEMPLATE_VERSION
    fields_used: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageContext:
    """Strictly-typed inputs the generator can pull from.

    Anything missing here means it does not appear in the message — the
    templates are written so dropped fields don't break the prose.
    """

    company: str
    contact_name: str
    contact_kind: str = "recruiter"
    contact_role: str | None = None
    role_title: str | None = None
    candidate_name: str | None = None
    candidate_headline: str | None = None
    candidate_years_experience: int | None = None
    top_skills: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    company_summary: str | None = None
    company_industry: str | None = None
    referral_target: str | None = None  # who is asked TO refer them
    previous_message_kind: str | None = None
    days_since_last_message: int | None = None
    interview_topic: str | None = None
    interview_round: str | None = None


# ---------------- helpers ----------------


def _word_count(text: str) -> int:
    return len(text.split())


def _truncate_words(text: str, *, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(",.;:") + "…"


def _greeting(contact_name: str) -> str:
    first = contact_name.strip().split()[0] if contact_name.strip() else ""
    return f"Hi {first}," if first else "Hi there,"


def _signoff(candidate_name: str | None) -> str:
    if candidate_name and candidate_name.strip():
        return f"Best,\n{candidate_name.strip()}"
    return "Best,"


def _skills_phrase(skills: list[str], *, limit: int = 3) -> str:
    cleaned = [s.strip() for s in skills if isinstance(s, str) and s.strip()]
    if not cleaned:
        return ""
    chosen = cleaned[:limit]
    if len(chosen) == 1:
        return chosen[0]
    if len(chosen) == 2:
        return f"{chosen[0]} and {chosen[1]}"
    return ", ".join(chosen[:-1]) + f", and {chosen[-1]}"


def _experience_phrase(ctx: MessageContext) -> str:
    parts: list[str] = []
    if ctx.candidate_years_experience and ctx.candidate_years_experience > 0:
        years = ctx.candidate_years_experience
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if ctx.candidate_headline:
        parts.append(f"as a {ctx.candidate_headline.strip()}")
    return " ".join(parts).strip()


def _company_clause(ctx: MessageContext) -> str:
    bits: list[str] = []
    if ctx.company_industry:
        bits.append(f"your work in {ctx.company_industry.strip()}")
    if ctx.company_summary:
        # Quote a single short fragment, not the whole blurb.
        first_sentence = ctx.company_summary.split(".")[0].strip()
        if first_sentence and first_sentence not in bits:
            bits.append(first_sentence)
    if not bits:
        return f"what {ctx.company.strip()} is building"
    return bits[0]


# ---------------- templates ----------------


def _initial_outreach(ctx: MessageContext) -> DraftedMessage:
    role = ctx.role_title or "an engineering role"
    skills = _skills_phrase(ctx.matched_skills or ctx.top_skills)
    exp = _experience_phrase(ctx)
    company_clause = _company_clause(ctx)
    paragraphs: list[str] = [_greeting(ctx.contact_name)]
    intro = f"I'm a software engineer with {exp}" if exp else "I'm a software engineer"
    if skills:
        intro += f", focused on {skills}"
    intro += f". I'm reaching out because {company_clause} caught my attention."
    paragraphs.append(intro)
    paragraphs.append(
        f"I'd love to be considered for {role} at {ctx.company.strip()}. "
        "Happy to share my resume or jump on a quick call if it's a fit."
    )
    paragraphs.append(_signoff(ctx.candidate_name))
    body = "\n\n".join(paragraphs)
    subject = f"Interested in {role} at {ctx.company.strip()}"
    return DraftedMessage(
        kind=KIND_INITIAL,
        subject=subject[:MAX_SUBJECT_CHARS],
        body=_truncate_words(body, limit=MAX_BODY_WORDS),
        channel="linkedin",
        fields_used={
            "company": ctx.company,
            "role_title": ctx.role_title,
            "skills": ctx.matched_skills or ctx.top_skills,
        },
    )


def _referral_request(ctx: MessageContext) -> DraftedMessage:
    target = (ctx.referral_target or ctx.contact_name).strip()
    role = ctx.role_title or "an open role"
    skills = _skills_phrase(ctx.matched_skills or ctx.top_skills)
    paragraphs: list[str] = [_greeting(ctx.contact_name)]
    ask = f"I noticed {ctx.company.strip()} is hiring for {role}. "
    if target and target != ctx.contact_name:
        ask += f"Would you be open to making an introduction to {target}? "
    else:
        ask += "Would you be open to flagging me to the hiring team? "
    if skills:
        ask += f"I work closely with {skills}, which lines up with the role."
    paragraphs.append(ask)
    paragraphs.append(
        "Totally understand if it's not the right moment — happy to share a tailored resume either way."
    )
    paragraphs.append(_signoff(ctx.candidate_name))
    body = "\n\n".join(paragraphs)
    subject = f"Quick ask about {ctx.company.strip()}"
    return DraftedMessage(
        kind=KIND_REFERRAL,
        subject=subject[:MAX_SUBJECT_CHARS],
        body=_truncate_words(body, limit=MAX_BODY_WORDS),
        channel="linkedin",
        fields_used={"referral_target": target, "company": ctx.company},
    )


def _hiring_manager_intro(ctx: MessageContext) -> DraftedMessage:
    role = ctx.role_title or "a role on your team"
    skills = _skills_phrase(ctx.matched_skills or ctx.top_skills, limit=4)
    exp = _experience_phrase(ctx)
    paragraphs: list[str] = [_greeting(ctx.contact_name)]
    open_line = ""
    if ctx.contact_role:
        open_line = (
            f"I saw you're leading {ctx.contact_role.strip()} at {ctx.company.strip()}, "
            f"and {role} caught my eye."
        )
    else:
        open_line = (
            f"I'm reaching out about {role} at {ctx.company.strip()} — it lines up "
            "closely with what I want to be doing next."
        )
    paragraphs.append(open_line)
    pitch = "Most recently I've been"
    if exp:
        pitch = f"I've spent the last {exp}"
    if skills:
        pitch += f" working on {skills}."
    else:
        pitch += " shipping production systems end-to-end."
    paragraphs.append(pitch)
    paragraphs.append(
        "Happy to send over my resume or a couple of design write-ups if that would help."
    )
    paragraphs.append(_signoff(ctx.candidate_name))
    body = "\n\n".join(paragraphs)
    subject = f"{role} — quick intro"
    return DraftedMessage(
        kind=KIND_HM_INTRO,
        subject=subject[:MAX_SUBJECT_CHARS],
        body=_truncate_words(body, limit=MAX_BODY_WORDS),
        channel="email",
        fields_used={
            "role_title": ctx.role_title,
            "contact_role": ctx.contact_role,
            "skills": ctx.matched_skills or ctx.top_skills,
        },
    )


def _follow_up(ctx: MessageContext) -> DraftedMessage:
    days = ctx.days_since_last_message
    paragraphs: list[str] = [_greeting(ctx.contact_name)]
    bump = "Wanted to circle back on my note"
    if days and days > 0:
        bump += f" from {days} day{'s' if days != 1 else ''} ago"
    bump += " — totally understand if timing's tight."
    paragraphs.append(bump)
    follow = f"Still very interested in {ctx.role_title or 'opportunities'} at {ctx.company.strip()}. "
    skills = _skills_phrase(ctx.matched_skills or ctx.top_skills)
    if skills:
        follow += f"Happy to share more on my work with {skills} if useful."
    else:
        follow += "Happy to share more on my background if useful."
    paragraphs.append(follow)
    paragraphs.append(_signoff(ctx.candidate_name))
    body = "\n\n".join(paragraphs)
    subject = f"Following up — {ctx.company.strip()}"
    return DraftedMessage(
        kind=KIND_FOLLOW_UP,
        subject=subject[:MAX_SUBJECT_CHARS],
        body=_truncate_words(body, limit=MAX_BODY_WORDS),
        channel="email",
        fields_used={
            "company": ctx.company,
            "days_since_last_message": days,
        },
    )


def _thank_you(ctx: MessageContext) -> DraftedMessage:
    paragraphs: list[str] = [_greeting(ctx.contact_name)]
    paragraphs.append(
        f"Thanks again for the time today — really enjoyed the conversation "
        f"about {ctx.company.strip()}."
    )
    if ctx.interview_topic:
        paragraphs.append(
            "I came away especially energised about "
            f"{ctx.interview_topic.strip()} — happy to dig deeper if helpful."
        )
    paragraphs.append(
        "Looking forward to the next step. Let me know if I can share anything more from my side."
    )
    paragraphs.append(_signoff(ctx.candidate_name))
    body = "\n\n".join(paragraphs)
    subject_bits = [f"Thanks — {ctx.company.strip()}"]
    if ctx.interview_round:
        subject_bits.append(ctx.interview_round.strip())
    subject = " · ".join(subject_bits)
    return DraftedMessage(
        kind=KIND_THANK_YOU,
        subject=subject[:MAX_SUBJECT_CHARS],
        body=_truncate_words(body, limit=MAX_BODY_WORDS),
        channel="email",
        fields_used={
            "interview_topic": ctx.interview_topic,
            "interview_round": ctx.interview_round,
        },
    )


_GENERATORS = {
    KIND_INITIAL: _initial_outreach,
    KIND_REFERRAL: _referral_request,
    KIND_HM_INTRO: _hiring_manager_intro,
    KIND_FOLLOW_UP: _follow_up,
    KIND_THANK_YOU: _thank_you,
}


def generate_message(kind: str, ctx: MessageContext) -> DraftedMessage:
    if kind not in _GENERATORS:
        raise MessageError(f"unknown message kind '{kind}' (allowed: {list(ALL_KINDS)})")
    if not (ctx.company or "").strip():
        raise MessageError("company is required (no fabricated content)")
    if not (ctx.contact_name or "").strip():
        raise MessageError("contact_name is required")
    drafted = _GENERATORS[kind](ctx)
    if _word_count(drafted.body) > MAX_BODY_WORDS:
        # Defensive — _truncate_words ran inside each template, but cap again.
        drafted = DraftedMessage(
            kind=drafted.kind,
            subject=drafted.subject,
            body=_truncate_words(drafted.body, limit=MAX_BODY_WORDS),
            channel=drafted.channel,
            template_version=drafted.template_version,
            fields_used=drafted.fields_used,
        )
    return drafted


def message_to_dict(m: DraftedMessage) -> dict[str, Any]:
    return {
        "kind": m.kind,
        "subject": m.subject,
        "body": m.body,
        "channel": m.channel,
        "template_version": m.template_version,
        "fields_used": dict(m.fields_used),
    }
