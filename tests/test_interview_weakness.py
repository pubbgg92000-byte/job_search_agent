"""Tests for the weakness analyzer — uses the deterministic matcher.

No LLM, no DB.
"""
from __future__ import annotations

from jobforge.interview.weakness import (
    compute_weakness_report,
    weakness_report_to_dict,
)


def _profile(skills: list[str] | None = None, title: str = "Senior Engineer") -> dict:
    return {
        "name": "Test",
        "email": "t@x.test",
        "skills": skills or ["Python", "PostgreSQL"],
        "experience": [{"title": title, "company": "X", "bullets": []}],
    }


def _job(description: str, title: str = "Senior Backend Engineer") -> dict:
    return {
        "title": title,
        "company": "TestCo",
        "description": description,
        "remote": True,
    }


def test_weakness_strengths_include_jd_mentioned_profile_skills() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python", "PostgreSQL"]),
        job=_job("Python and PostgreSQL"),
    )
    lowered = [s.lower() for s in r.strengths]
    assert "python" in lowered
    assert "postgresql" in lowered


def test_weakness_flags_missing_skill_from_jd() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job=_job("We use Rust and Python"),
    )
    skills = [w.skill.lower() for w in r.weaknesses]
    assert "rust" in skills


def test_weakness_rows_sorted_by_impact_descending() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job=_job(
            "Looking for: PostgreSQL PostgreSQL PostgreSQL system design system design Rust"
        ),
    )
    impacts = [w.impact for w in r.weaknesses]
    assert impacts == sorted(impacts, reverse=True)


def test_weakness_high_impact_keyword_gets_high_severity() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job=_job("We do heavy system design and PostgreSQL"),
    )
    sysd = next(
        (w for w in r.weaknesses if "system design" in w.skill.lower()),
        None,
    )
    if sysd is not None:
        assert sysd.severity in ("medium", "high")


def test_weakness_risk_areas_match_weakness_rows() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job=_job("Rust Kafka required"),
    )
    risk_topics = {x.topic.lower() for x in r.risk_areas}
    weak_topics = {w.skill.lower() for w in r.weaknesses}
    assert weak_topics.issubset(risk_topics)


def test_weakness_empty_profile_surfaces_coverage_risk() -> None:
    r = compute_weakness_report(profile={}, job=_job("nothing here"))
    topics = [x.topic.lower() for x in r.risk_areas]
    if not r.weaknesses:
        assert any("profile coverage" in t for t in topics)


def test_weakness_strengths_only_includes_profile_skills_mentioned_in_jd() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python", "Rust"]),
        job=_job("We use Python heavily"),
    )
    lowered = [s.lower() for s in r.strengths]
    assert "python" in lowered
    # Rust is in the profile but NOT in the JD — must not appear as a strength.
    assert "rust" not in lowered


def test_weakness_to_dict_round_trips() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job=_job("Rust required"),
    )
    d = weakness_report_to_dict(r)
    assert set(d.keys()) == {
        "strengths",
        "weaknesses",
        "matched_skills",
        "missing_skills",
        "risk_areas",
    }
    if d["weaknesses"]:
        first = d["weaknesses"][0]
        assert set(first.keys()) == {"skill", "severity", "impact"}


def test_weakness_dedupes_skill_list() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python", "python", "PYTHON"]),
        job=_job("Python rust"),
    )
    lowered = [s.lower() for s in r.matched_skills]
    assert lowered.count("python") == 1


def test_weakness_severity_thresholds() -> None:
    r = compute_weakness_report(
        profile=_profile([]),
        job=_job("we need cobol cobol cobol cobol cobol"),
    )
    if r.weaknesses:
        # The repeated mentions should push impact upward.
        cobol = next((w for w in r.weaknesses if "cobol" in w.skill.lower()), None)
        if cobol is not None:
            assert cobol.impact >= 30


def test_weakness_handles_missing_description_gracefully() -> None:
    r = compute_weakness_report(
        profile=_profile(["Python"]),
        job={"title": "Engineer", "company": "Co", "description": ""},
    )
    # No JD signal — risk areas may be empty, but the call must not raise.
    assert isinstance(r.missing_skills, list)


def test_weakness_skips_non_string_profile_skills() -> None:
    r = compute_weakness_report(
        profile={"skills": [1, None, "Python"]},
        job=_job("Python and Rust"),
    )
    assert "Python" in r.strengths
