"""Unit tests for the outreach status flow + message generators (no DB)."""
from __future__ import annotations

import pytest

from jobforge.outreach.messages import (
    ALL_KINDS,
    KIND_FOLLOW_UP,
    KIND_HM_INTRO,
    KIND_INITIAL,
    KIND_REFERRAL,
    KIND_THANK_YOU,
    MAX_BODY_WORDS,
    MAX_SUBJECT_CHARS,
    MessageContext,
    MessageError,
    generate_message,
    message_to_dict,
)
from jobforge.outreach.status import (
    ALL_STATUSES,
    STATUS_CLOSED,
    STATUS_DRAFTED,
    STATUS_IGNORED,
    STATUS_INTERVIEW,
    STATUS_REPLIED,
    STATUS_SENT,
    is_forward_transition,
    is_terminal,
    is_valid_status,
)

# ---------------- status flow ----------------


def test_is_valid_status_for_all_statuses() -> None:
    for s in ALL_STATUSES:
        assert is_valid_status(s)
    assert is_valid_status("not-a-status") is False


def test_is_forward_drafted_to_sent() -> None:
    assert is_forward_transition(STATUS_DRAFTED, STATUS_SENT) is True


def test_is_forward_sent_to_replied() -> None:
    assert is_forward_transition(STATUS_SENT, STATUS_REPLIED) is True


def test_is_forward_replied_to_interview() -> None:
    assert is_forward_transition(STATUS_REPLIED, STATUS_INTERVIEW) is True


def test_is_forward_rejects_backwards() -> None:
    assert is_forward_transition(STATUS_REPLIED, STATUS_DRAFTED) is False


def test_is_forward_ignored_can_loop_back_to_sent() -> None:
    # A re-engage is allowed forward.
    assert is_forward_transition(STATUS_IGNORED, STATUS_SENT) is True


def test_is_forward_sent_to_closed_allowed() -> None:
    assert is_forward_transition(STATUS_SENT, STATUS_CLOSED) is True


def test_is_terminal_only_closed() -> None:
    assert is_terminal(STATUS_CLOSED) is True
    for s in (STATUS_DRAFTED, STATUS_SENT, STATUS_REPLIED, STATUS_INTERVIEW, STATUS_IGNORED):
        assert is_terminal(s) is False


# ---------------- generator base ----------------


def _ctx(
    *,
    company: str = "Acme",
    contact_name: str = "Sam Tan",
    role_title: str = "Senior Backend Engineer",
    skills: list[str] | None = None,
    candidate_name: str | None = "Rahul",
    candidate_headline: str | None = "backend engineer",
    candidate_years_experience: int | None = 8,
    company_summary: str | None = "Acme builds fintech infra.",
    company_industry: str | None = "fintech",
    referral_target: str | None = None,
    days_since_last_message: int | None = None,
    interview_topic: str | None = None,
    interview_round: str | None = None,
    contact_role: str | None = None,
) -> MessageContext:
    return MessageContext(
        company=company,
        contact_name=contact_name,
        contact_role=contact_role,
        role_title=role_title,
        candidate_name=candidate_name,
        candidate_headline=candidate_headline,
        candidate_years_experience=candidate_years_experience,
        top_skills=skills or ["Python", "PostgreSQL", "TypeScript"],
        matched_skills=skills or ["Python", "PostgreSQL"],
        company_summary=company_summary,
        company_industry=company_industry,
        referral_target=referral_target,
        days_since_last_message=days_since_last_message,
        interview_topic=interview_topic,
        interview_round=interview_round,
    )


def test_generate_initial_outreach_includes_company_name() -> None:
    msg = generate_message(KIND_INITIAL, _ctx())
    assert "Acme" in msg.body
    assert msg.subject and "Acme" in msg.subject


def test_generate_initial_outreach_includes_role_title() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(role_title="Staff Platforms Engineer"))
    assert "Staff Platforms Engineer" in msg.body


def test_generate_initial_outreach_uses_matched_skills_phrase() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(skills=["GraphQL", "Rust"]))
    assert "GraphQL" in msg.body
    assert "Rust" in msg.body


def test_generate_initial_outreach_word_cap() -> None:
    msg = generate_message(KIND_INITIAL, _ctx())
    assert len(msg.body.split()) <= MAX_BODY_WORDS


def test_generate_initial_subject_cap() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(company="A" * 250))
    assert msg.subject is None or len(msg.subject) <= MAX_SUBJECT_CHARS


def test_generate_referral_request_includes_company_name() -> None:
    msg = generate_message(KIND_REFERRAL, _ctx(referral_target="Asha"))
    assert "Acme" in msg.body
    assert "Asha" in msg.body


def test_generate_referral_request_falls_back_to_contact_if_no_target() -> None:
    msg = generate_message(KIND_REFERRAL, _ctx(referral_target=None))
    assert "Sam" in msg.body  # first-name greeting


def test_generate_hm_intro_uses_contact_role_when_present() -> None:
    msg = generate_message(KIND_HM_INTRO, _ctx(contact_role="Director of Engineering"))
    assert "Director of Engineering" in msg.body


def test_generate_hm_intro_works_without_contact_role() -> None:
    msg = generate_message(KIND_HM_INTRO, _ctx(contact_role=None))
    assert "Acme" in msg.body


def test_generate_follow_up_mentions_days_when_provided() -> None:
    msg = generate_message(KIND_FOLLOW_UP, _ctx(days_since_last_message=10))
    assert "10 day" in msg.body


def test_generate_follow_up_singular_day_when_one() -> None:
    msg = generate_message(KIND_FOLLOW_UP, _ctx(days_since_last_message=1))
    assert "1 day" in msg.body


def test_generate_follow_up_works_without_days() -> None:
    msg = generate_message(KIND_FOLLOW_UP, _ctx(days_since_last_message=None))
    assert msg.kind == KIND_FOLLOW_UP
    assert "Acme" in msg.body


def test_generate_thank_you_includes_topic_when_provided() -> None:
    msg = generate_message(
        KIND_THANK_YOU,
        _ctx(interview_topic="distributed systems", interview_round="onsite"),
    )
    assert "distributed systems" in msg.body
    assert msg.subject and "onsite" in msg.subject.lower()


def test_generate_thank_you_works_without_topic() -> None:
    msg = generate_message(KIND_THANK_YOU, _ctx())
    assert "Acme" in msg.body


def test_generate_message_unknown_kind_raises() -> None:
    with pytest.raises(MessageError):
        generate_message("not-a-kind", _ctx())


def test_generate_message_missing_company_raises() -> None:
    with pytest.raises(MessageError):
        generate_message(KIND_INITIAL, _ctx(company=""))


def test_generate_message_missing_contact_name_raises() -> None:
    with pytest.raises(MessageError):
        generate_message(KIND_INITIAL, _ctx(contact_name=""))


def test_generate_initial_signoff_uses_candidate_name() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(candidate_name="Priya"))
    assert "Priya" in msg.body


def test_generate_initial_signoff_handles_missing_candidate_name() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(candidate_name=None))
    assert "Best," in msg.body


def test_generate_all_kinds_produce_a_message() -> None:
    for kind in ALL_KINDS:
        msg = generate_message(kind, _ctx(referral_target="X"))
        assert msg.kind == kind
        assert msg.body.strip()
        assert len(msg.body.split()) <= MAX_BODY_WORDS


def test_message_to_dict_keys() -> None:
    msg = generate_message(KIND_INITIAL, _ctx())
    d = message_to_dict(msg)
    expected = {"kind", "subject", "body", "channel", "template_version", "fields_used"}
    assert set(d.keys()) == expected


def test_initial_outreach_no_skills_still_produces_message() -> None:
    msg = generate_message(
        KIND_INITIAL,
        MessageContext(company="Acme", contact_name="Sam", role_title="Eng"),
    )
    assert "Acme" in msg.body


def test_generate_does_not_leak_placeholder_braces() -> None:
    """Truthful-only: empty fields must NOT leave `[name]`-style placeholders."""
    for kind in ALL_KINDS:
        msg = generate_message(
            kind,
            MessageContext(company="Acme", contact_name="Sam"),
        )
        assert "[" not in msg.body
        assert "{" not in msg.body
        assert "your name" not in msg.body.lower()
        assert "your company" not in msg.body.lower()


def test_generate_initial_outreach_does_not_invent_skills_when_absent() -> None:
    """No skills passed in → no skills mentioned. We do not fabricate."""
    msg = generate_message(
        KIND_INITIAL,
        MessageContext(
            company="Acme",
            contact_name="Sam",
            role_title="Engineer",
            top_skills=[],
            matched_skills=[],
        ),
    )
    for forbidden in ("Python", "PostgreSQL", "TypeScript", "Rust", "GraphQL"):
        assert forbidden not in msg.body


def test_generate_thank_you_subject_includes_round() -> None:
    msg = generate_message(
        KIND_THANK_YOU,
        _ctx(interview_round="hiring manager screen"),
    )
    assert msg.subject is not None
    assert "hiring manager screen" in msg.subject.lower()


def test_generate_initial_outreach_channel_is_linkedin() -> None:
    assert generate_message(KIND_INITIAL, _ctx()).channel == "linkedin"


def test_generate_hm_intro_channel_is_email() -> None:
    assert generate_message(KIND_HM_INTRO, _ctx()).channel == "email"


def test_generate_thank_you_channel_is_email() -> None:
    assert generate_message(KIND_THANK_YOU, _ctx()).channel == "email"


def test_generate_initial_outreach_template_version_set() -> None:
    msg = generate_message(KIND_INITIAL, _ctx())
    assert msg.template_version == "v1"


def test_generate_initial_outreach_fields_used_tracks_inputs() -> None:
    msg = generate_message(KIND_INITIAL, _ctx())
    assert "company" in msg.fields_used
    assert msg.fields_used["company"] == "Acme"


def test_generate_initial_outreach_handles_zero_years_experience() -> None:
    msg = generate_message(
        KIND_INITIAL,
        _ctx(candidate_years_experience=0, candidate_headline="recent grad"),
    )
    # The years phrase must drop entirely, but the headline still appears.
    assert "0 year" not in msg.body


def test_generate_initial_outreach_handles_single_year_experience() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(candidate_years_experience=1))
    assert "1 year" in msg.body
    assert "1 years" not in msg.body


def test_generate_initial_outreach_includes_industry_when_present() -> None:
    msg = generate_message(
        KIND_INITIAL, _ctx(company_industry="healthcare", company_summary=None)
    )
    assert "healthcare" in msg.body


def test_generate_initial_outreach_falls_back_when_no_company_clause() -> None:
    msg = generate_message(
        KIND_INITIAL,
        _ctx(company_industry=None, company_summary=None),
    )
    # No clause means we say what {company} is building.
    assert "Acme" in msg.body


def test_subject_truncation_for_long_company_does_not_crash() -> None:
    msg = generate_message(KIND_INITIAL, _ctx(company="C" * 500))
    assert msg.subject is not None
    assert len(msg.subject) <= MAX_SUBJECT_CHARS
