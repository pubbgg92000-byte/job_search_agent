"""End-to-end test of the tailoring pipeline.

PRD launch gate: "one end-to-end test: resume upload → profile parse → JD analyze →
tailor → ATS score → save application → daily report."

We hit a real Postgres (from docker-compose) for DB writes. The three LLM-calling
agent functions are monkeypatched so the test is deterministic and offline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select

from jobforge.agents import resume_parser
from jobforge.config import get_settings
from jobforge.db.models import Job, Profile, TailoredArtifact, User
from jobforge.db.session import session_scope
from jobforge.pipelines import tailor_for_jd as pipeline_module
from jobforge.pipelines.tailor_for_jd import DailyRunLimitExceeded, tailor_for_jd

pytestmark = pytest.mark.asyncio


# Realistic mocked LLM responses for a Node.js / Svelte JD.
_FAKE_PROFILE = {
    "name": "Rahul Sample",
    "email": "rahul@example.com",
    "skills": ["Node.js", "TypeScript", "PostgreSQL", "Svelte", "REST APIs"],
    "summary": "Senior full-stack developer with Node.js + PostgreSQL.",
    "experience": [
        {
            "company": "Acme Cloud",
            "title": "Senior Software Engineer",
            "bullets": [
                "Shipped Node.js + TypeScript services on AWS Lambda.",
                "Migrated dashboard from React to SvelteKit.",
            ],
        }
    ],
    "projects": [],
    "education": [{"institution": "IIT Madras", "degree": "B.Tech CS"}],
    "certifications": [],
}

_FAKE_JD = {
    "title": "Senior Full-Stack Developer",
    "company": "Hypothetical Inc",
    "location": "Remote",
    "remote": True,
    "summary": "Lead frontend on SvelteKit + Node.js + PostgreSQL.",
    "required_skills": ["Node.js", "TypeScript", "Svelte", "PostgreSQL", "REST APIs"],
    "preferred_skills": ["Docker"],
    "keywords": ["GitHub Actions"],
    "seniority": "senior",
}


async def _ensure_user_row(user_id: int) -> None:
    async with session_scope() as session:
        existing = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                User(id=user_id, name="Rahul Test", email=f"e2e-{user_id}@example.com")
            )


async def _reset_user_state(user_id: int) -> None:
    """Wipe any artifacts/jobs/profiles for a test user so each test starts clean."""
    async with session_scope() as session:
        await session.execute(delete(TailoredArtifact).where(TailoredArtifact.user_id == user_id))
        await session.execute(delete(Job).where(Job.user_id == user_id))
        await session.execute(delete(Profile).where(Profile.user_id == user_id))


async def _seed_profile(user_id: int) -> int:
    async with session_scope() as session:
        prof = Profile(
            user_id=user_id,
            source_filename="e2e.pdf",
            raw_resume_text="Node.js TypeScript PostgreSQL Svelte REST APIs",
            parsed_json=_FAKE_PROFILE,
        )
        session.add(prof)
        await session.flush()
        return prof.id


def _patch_llm_agents(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tailored_outputs: list[str],
    cover_letter: str = "Hi, I'm interested. Sincerely, Rahul.",
) -> dict[str, int]:
    """Patch the LLM-calling agents to return canned outputs.

    Returns a counter dict so the test can assert call counts.
    """
    counts = {"analyze_jd": 0, "tailor_resume": 0, "write_cover_letter": 0}
    queue = list(tailored_outputs)

    async def fake_analyze(jd_text: str) -> dict[str, Any]:
        counts["analyze_jd"] += 1
        return _FAKE_JD

    async def fake_tailor(**_: Any) -> str:
        counts["tailor_resume"] += 1
        return queue.pop(0)

    async def fake_cover(**_: Any) -> str:
        counts["write_cover_letter"] += 1
        return cover_letter

    monkeypatch.setattr(pipeline_module, "analyze_jd", fake_analyze)
    monkeypatch.setattr(pipeline_module, "tailor_resume", fake_tailor)
    monkeypatch.setattr(pipeline_module, "write_cover_letter", fake_cover)
    return counts


async def test_pipeline_end_to_end_writes_artifact_and_returns_scores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    user_id = 9001
    monkeypatch.setattr(settings, "sole_user_id", user_id, raising=False)
    # Generous limit so the rate-limit guard doesn't fire.
    monkeypatch.setattr(settings, "max_runs_per_day", 50, raising=False)

    await _ensure_user_row(user_id)
    await _reset_user_state(user_id)
    profile_id = await _seed_profile(user_id)

    # First tailoring covers all required skills + the preferred + keyword,
    # so the rescore is high and no retry is needed.
    tailored_md = (
        "# Rahul Sample\n## Skills\nNode.js, TypeScript, Svelte, PostgreSQL, REST APIs, "
        "Docker, GitHub Actions\n## Experience\n- Built Node.js services."
    )
    counts = _patch_llm_agents(monkeypatch, tailored_outputs=[tailored_md])

    result = await tailor_for_jd(
        profile_id=profile_id,
        jd_text="Looking for Node.js + Svelte engineer.",
        user_id=user_id,
        company_name="Hypothetical Inc",
    )

    assert counts == {"analyze_jd": 1, "tailor_resume": 1, "write_cover_letter": 1}
    assert result.company == "Hypothetical Inc"
    assert result.title == "Senior Full-Stack Developer"
    assert result.score_after >= 75, "tailored score should clear TARGET_SCORE"
    assert result.score_after >= result.score_before

    # DB writes happened:
    async with session_scope() as session:
        job = (
            await session.execute(select(Job).where(Job.id == result.job_id))
        ).scalar_one()
        assert job.user_id == user_id
        assert job.parsed_json["title"] == "Senior Full-Stack Developer"

        artifact = (
            await session.execute(
                select(TailoredArtifact).where(TailoredArtifact.id == result.artifact_id)
            )
        ).scalar_one()
        assert artifact.profile_id == profile_id
        assert artifact.ats_score == result.score_after
        assert artifact.tailored_resume_md == tailored_md
        assert artifact.cover_letter_md == "Hi, I'm interested. Sincerely, Rahul."
        assert artifact.model_used == settings.model_tailoring


async def test_pipeline_retries_when_first_tailoring_falls_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    user_id = 9002
    monkeypatch.setattr(settings, "sole_user_id", user_id, raising=False)
    monkeypatch.setattr(settings, "max_runs_per_day", 50, raising=False)

    await _ensure_user_row(user_id)
    await _reset_user_state(user_id)
    profile_id = await _seed_profile(user_id)

    weak = "# Rahul\n## Skills\nNode.js\n## Experience\n- Stuff."  # misses TS / Svelte / PG / REST
    strong = (
        "# Rahul\n## Skills\nNode.js, TypeScript, Svelte, PostgreSQL, REST APIs, Docker, "
        "GitHub Actions\n## Experience\n- Stuff."
    )
    counts = _patch_llm_agents(monkeypatch, tailored_outputs=[weak, strong])

    result = await tailor_for_jd(
        profile_id=profile_id,
        jd_text="Need Node.js+Svelte engineer",
        user_id=user_id,
    )

    assert counts["tailor_resume"] == 2, "expected one retry pass"
    assert result.score_after >= 75


async def test_pipeline_enforces_daily_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    user_id = 9003
    monkeypatch.setattr(settings, "sole_user_id", user_id, raising=False)
    # Set the limit at exactly 1 so the second run fails.
    monkeypatch.setattr(settings, "max_runs_per_day", 1, raising=False)

    await _ensure_user_row(user_id)
    await _reset_user_state(user_id)
    profile_id = await _seed_profile(user_id)

    strong = (
        "# Rahul\n## Skills\nNode.js, TypeScript, Svelte, PostgreSQL, REST APIs, Docker, "
        "GitHub Actions\n## Experience\n- Stuff."
    )
    _patch_llm_agents(monkeypatch, tailored_outputs=[strong, strong, strong])

    # First run succeeds.
    await tailor_for_jd(
        profile_id=profile_id, jd_text="JD text long enough", user_id=user_id
    )
    # Second run should be rejected — exactly 1 artifact already created in 24h.
    with pytest.raises(DailyRunLimitExceeded):
        await tailor_for_jd(
            profile_id=profile_id, jd_text="JD text long enough", user_id=user_id
        )


async def test_pipeline_uses_parsed_jd_company_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    user_id = 9004
    monkeypatch.setattr(settings, "sole_user_id", user_id, raising=False)
    monkeypatch.setattr(settings, "max_runs_per_day", 50, raising=False)

    await _ensure_user_row(user_id)
    await _reset_user_state(user_id)
    profile_id = await _seed_profile(user_id)

    strong = (
        "# Rahul\n## Skills\nNode.js, TypeScript, Svelte, PostgreSQL, REST APIs, Docker, "
        "GitHub Actions"
    )
    _patch_llm_agents(monkeypatch, tailored_outputs=[strong])

    result = await tailor_for_jd(
        profile_id=profile_id, jd_text="JD text long enough", user_id=user_id
    )
    # company_name not passed → falls back to JD-parsed company
    assert result.company == "Hypothetical Inc"


async def test_ingest_through_pipeline_uses_real_pdf_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closes the loop: PDF extraction → parse_resume → store profile → pipeline run.

    parse_resume (the LLM-backed structuring step) is monkeypatched; everything
    else is real.
    """
    settings = get_settings()
    user_id = 9005
    monkeypatch.setattr(settings, "sole_user_id", user_id, raising=False)
    monkeypatch.setattr(settings, "max_runs_per_day", 50, raising=False)

    await _ensure_user_row(user_id)
    await _reset_user_state(user_id)

    async def fake_parse_resume(_raw_text: str) -> dict[str, Any]:
        return _FAKE_PROFILE

    monkeypatch.setattr(resume_parser, "parse_resume", fake_parse_resume)

    fixture = Path(__file__).parent / "fixtures" / "sample_resume.pdf"
    raw_text, parsed = await resume_parser.parse_resume_pdf(fixture)
    assert "Rahul" in raw_text
    assert parsed["skills"]

    async with session_scope() as session:
        prof = Profile(
            user_id=user_id,
            source_filename="sample_resume.pdf",
            raw_resume_text=raw_text,
            parsed_json=parsed,
        )
        session.add(prof)
        await session.flush()
        profile_id = prof.id

    strong = (
        "# Rahul\n## Skills\nNode.js, TypeScript, Svelte, PostgreSQL, REST APIs, Docker, "
        "GitHub Actions"
    )
    _patch_llm_agents(monkeypatch, tailored_outputs=[strong])

    result = await tailor_for_jd(
        profile_id=profile_id,
        jd_text="Looking for a senior full-stack engineer.",
        user_id=user_id,
    )
    assert result.artifact_id > 0
    assert result.score_after >= 75
