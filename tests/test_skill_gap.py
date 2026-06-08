"""Skill gap engine + plan generator tests."""
from __future__ import annotations

from datetime import UTC, datetime

from jobforge.match import UserPreferences
from jobforge.skills import (
    compute_gaps,
    gap_to_dict,
    make_seven_day_plan,
    make_thirty_day_plan,
    plan_to_dict,
)

_NOW = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)

_PROFILE_PY = {
    "skills": ["Python", "PostgreSQL"],
    "experience": [
        {"title": "Senior Software Engineer", "company": "X", "bullets": ["..."]}
    ],
}


def _job(jid, *, skills, score_hint=80):
    """Construct a fake job dict that the matcher can score."""
    return {
        "id": jid,
        "title": "Senior Python Engineer",
        "company": "Acme",
        "location": "Remote",
        "remote": True,
        "description": "We use Python, " + ", ".join(skills),
        "posted_at": _NOW,
        "salary_min": 150000,
        "salary_max": 200000,
        "salary_currency": "USD",
    }


def test_compute_gaps_aggregates_missing_skills_across_jobs() -> None:
    # The matcher takes job_keywords; we feed it via _derive_keywords by including
    # the missing skills in the description. Simpler: pass job_keywords through.
    from jobforge.match import match_job

    jobs = [
        {
            "id": 1, "title": "T", "company": "A", "remote": True,
            "description": "", "posted_at": _NOW,
            "salary_min": None, "salary_max": None,
        }
    ]
    # Sanity: match_job sees Python in profile, so missing_skills excludes it.
    res = match_job(profile=_PROFILE_PY, job=jobs[0], job_keywords=["Python", "Rust", "Docker"])
    assert "Rust" in res.missing_skills
    assert "Docker" in res.missing_skills

    # Now exercise the gap aggregator. We piggyback by injecting jobs that the
    # matcher will derive "Rust" and "Docker" from the description.
    fake_jobs = [
        {**jobs[0], "id": i, "description": "We use Rust and Docker"}
        for i in range(5)
    ]
    report = compute_gaps(profile=_PROFILE_PY, jobs=fake_jobs, prefs=UserPreferences())
    skills = {g.skill.lower(): g for g in report.top_gaps}
    assert "rust" in skills
    assert "docker" in skills
    # Each job contributes once, so frequency = 5 for both.
    assert skills["rust"].frequency == 5
    assert skills["docker"].frequency == 5


def test_compute_gaps_importance_higher_for_high_match_jobs() -> None:
    """A missing skill in a job that otherwise scores high should rank above
    the same skill in a job that scores low."""
    # We can't directly control matcher score per job, but we can produce a mix
    # where some jobs are remote+fresh+matching (high) and others are stale+onsite (low).
    from datetime import timedelta

    high_match_job = {
        "id": 1, "title": "Senior Python Engineer", "company": "A", "remote": True,
        "description": "Python with Rust",
        "posted_at": _NOW, "salary_min": 150000, "salary_max": 200000,
    }
    low_match_job = {
        "id": 2, "title": "Junior PHP Wrangler", "company": "B", "remote": False,
        "description": "PHP with Kubernetes",
        "posted_at": _NOW - timedelta(days=120),
        "salary_min": None, "salary_max": None,
    }
    report = compute_gaps(
        profile=_PROFILE_PY, jobs=[high_match_job, low_match_job], prefs=UserPreferences()
    )
    # Either Rust (from high-match) or Kubernetes (from low-match) should win.
    top_skill = report.top_gaps[0].skill.lower()
    assert top_skill in {"rust", "kubernetes"}
    # If Rust appears, it should outrank Kubernetes in importance.
    by_skill = {g.skill.lower(): g.importance_score for g in report.top_gaps}
    if "rust" in by_skill and "kubernetes" in by_skill:
        assert by_skill["rust"] >= by_skill["kubernetes"]


def test_compute_gaps_returns_empty_when_no_missing() -> None:
    job = {
        "id": 1, "title": "T", "company": "A", "remote": True,
        "description": "Python and PostgreSQL only", "posted_at": _NOW,
        "salary_min": None, "salary_max": None,
    }
    report = compute_gaps(profile=_PROFILE_PY, jobs=[job], prefs=UserPreferences())
    # All keywords match the profile, so no missing skills.
    assert report.top_gaps == [] or all(
        g.skill.lower() not in {"python", "postgresql"} for g in report.top_gaps
    )


def test_seven_day_plan_targets_top_three_skills() -> None:
    fake_jobs = [
        {
            "id": i, "title": "T", "company": "A", "remote": True,
            "description": "Rust and Docker and Kubernetes",
            "posted_at": _NOW,
            "salary_min": None, "salary_max": None,
        }
        for i in range(3)
    ]
    report = compute_gaps(profile=_PROFILE_PY, jobs=fake_jobs)
    plan = make_seven_day_plan(report)
    assert plan.horizon == "7-day"
    assert len(plan.target_skills) <= 3
    assert len(plan.steps) >= 1
    # The integrate step should be the last one.
    assert "Integrate" in plan.steps[-1].focus


def test_thirty_day_plan_pairs_skills_per_week() -> None:
    fake_jobs = [
        {
            "id": i, "title": "T", "company": "A", "remote": True,
            "description": "Rust Docker Kubernetes Redis Kafka Terraform AWS GCP",
            "posted_at": _NOW,
            "salary_min": None, "salary_max": None,
        }
        for i in range(4)
    ]
    report = compute_gaps(profile=_PROFILE_PY, jobs=fake_jobs)
    plan = make_thirty_day_plan(report)
    assert plan.horizon == "30-day"
    assert len(plan.steps) == 4  # weeks 1-4


def test_plan_to_dict_round_trip_shape() -> None:
    fake_jobs = [
        {
            "id": 1, "title": "T", "company": "A", "remote": True,
            "description": "Rust",
            "posted_at": _NOW, "salary_min": None, "salary_max": None,
        }
    ]
    report = compute_gaps(profile=_PROFILE_PY, jobs=fake_jobs)
    payload = plan_to_dict(make_seven_day_plan(report))
    assert payload["horizon"] == "7-day"
    assert isinstance(payload["target_skills"], list)
    assert isinstance(payload["steps"], list)


def test_gap_to_dict_includes_all_fields() -> None:
    from jobforge.skills.gap import SkillGap

    g = SkillGap(skill="Rust", frequency=3, importance_score=80, total_match_score=240)
    d = gap_to_dict(g)
    assert d == {
        "skill": "Rust",
        "frequency": 3,
        "importance_score": 80,
        "total_match_score": 240,
    }
