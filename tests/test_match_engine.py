"""Tests for the deterministic match engine."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jobforge.match import WEIGHTS, UserPreferences, match_job

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)

_PROFILE = {
    "skills": ["Python", "Go", "PostgreSQL", "Docker", "Kubernetes"],
    "experience": [
        {"title": "Senior Software Engineer", "company": "X", "bullets": ["..."]},
    ],
}


def _job(**overrides):
    base = {
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "remote": True,
        "description": "We use Python and PostgreSQL on Kubernetes.",
        "posted_at": NOW - timedelta(days=2),
        "salary_min": 150000,
        "salary_max": 200000,
        "salary_currency": "USD",
    }
    base.update(overrides)
    return base


def test_weights_sum_to_one() -> None:
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_perfect_match_scores_near_top() -> None:
    job = _job()
    res = match_job(
        profile=_PROFILE,
        job=job,
        job_keywords=["Python", "PostgreSQL", "Kubernetes"],
        now=NOW,
    )
    assert res.skill_match == 100
    assert res.seniority_match == 100
    assert res.score >= 90  # all axes ≥ ~85


def test_missing_skill_drops_skill_axis_and_lists_in_missing() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(),
        job_keywords=["Python", "Rust", "Erlang"],
        now=NOW,
    )
    assert res.skill_match < 100
    assert "Rust" in res.missing_skills
    assert "Erlang" in res.missing_skills


def test_seniority_gap_lowers_seniority_axis() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(title="Principal Distinguished Engineer"),
        job_keywords=["Python"],
        now=NOW,
    )
    # principal vs senior = 2 levels apart (we infer 'principal' from title) → 100 - 60
    assert res.seniority_match <= 70


def test_unknown_seniority_returns_neutral() -> None:
    res = match_job(
        profile={"skills": ["Python"], "experience": []},  # no seniority signal
        job=_job(title="Software Engineer"),
        job_keywords=["Python"],
        now=NOW,
    )
    assert 50 <= res.seniority_match <= 80


def test_location_match_with_matching_location() -> None:
    prefs = UserPreferences(locations=("Bengaluru",))
    res = match_job(
        profile=_PROFILE,
        job=_job(location="Bengaluru, India", remote=False),
        prefs=prefs,
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.location_match == 100


def test_location_mismatch_lowers_axis() -> None:
    prefs = UserPreferences(locations=("Bengaluru",))
    res = match_job(
        profile=_PROFILE,
        job=_job(location="Berlin", remote=False),
        prefs=prefs,
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.location_match <= 40


def test_remote_preference_rewards_remote_jobs() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(remote=True),
        prefs=UserPreferences(prefers_remote=True),
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.remote_match == 100


def test_remote_preference_punishes_onsite_jobs() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(remote=False),
        prefs=UserPreferences(prefers_remote=True),
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.remote_match <= 50


def test_salary_meets_floor_full_credit() -> None:
    prefs = UserPreferences(salary_min_required=100000)
    res = match_job(
        profile=_PROFILE,
        job=_job(salary_min=120000, salary_max=140000),
        prefs=prefs,
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.salary_match == 100


def test_salary_below_floor_partial_credit() -> None:
    prefs = UserPreferences(salary_min_required=200000)
    res = match_job(
        profile=_PROFILE,
        job=_job(salary_min=80000, salary_max=100000),
        prefs=prefs,
        job_keywords=["Python"],
        now=NOW,
    )
    assert 30 <= res.salary_match <= 60


def test_missing_salary_is_neutral() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(salary_min=None, salary_max=None),
        prefs=UserPreferences(salary_min_required=120000),
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.salary_match == 60


def test_freshness_full_credit_for_today() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(posted_at=NOW - timedelta(hours=12)),
        job_keywords=["Python"],
        now=NOW,
    )
    assert res.freshness == 100


def test_freshness_decays_with_age() -> None:
    fresh = match_job(
        profile=_PROFILE,
        job=_job(posted_at=NOW - timedelta(days=3)),
        job_keywords=["Python"],
        now=NOW,
    ).freshness
    stale = match_job(
        profile=_PROFILE,
        job=_job(posted_at=NOW - timedelta(days=50)),
        job_keywords=["Python"],
        now=NOW,
    ).freshness
    ancient = match_job(
        profile=_PROFILE,
        job=_job(posted_at=NOW - timedelta(days=120)),
        job_keywords=["Python"],
        now=NOW,
    ).freshness
    assert fresh > stale > ancient


def test_derived_keywords_picks_up_tech_terms_from_title() -> None:
    # No explicit keyword list passed; the engine should still find "Python" in the title.
    res = match_job(
        profile=_PROFILE,
        job=_job(title="Senior Python Engineer", description="N/A"),
        now=NOW,
    )
    # Python is in the profile, so the auto-derived skill match should be high.
    assert res.skill_match >= 70


def test_final_score_is_weighted_combo_in_range() -> None:
    res = match_job(
        profile=_PROFILE,
        job=_job(),
        job_keywords=["Python", "Rust"],  # 1/2 hit
        now=NOW,
    )
    assert 0 <= res.score <= 100
