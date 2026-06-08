"""Application agent foundation — detector + mapper + package assembly."""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from jobforge.application_agent import (
    ATSPlatform,
    FieldMapper,
    PackageError,
    detect_platform,
    map_profile,
    prepare_package,
)
from jobforge.db.models import DiscoveredJob, Profile, User
from jobforge.db.session import session_scope

# --------------------------- detector -------------------------------------


def test_detect_greenhouse_from_boards_subdomain() -> None:
    assert detect_platform("https://boards.greenhouse.io/stripe/jobs/123") == ATSPlatform.GREENHOUSE


def test_detect_lever_from_jobs_subdomain() -> None:
    assert detect_platform("https://jobs.lever.co/netflix/abc-123") == ATSPlatform.LEVER


def test_detect_ashby_from_subdomain() -> None:
    assert detect_platform("https://jobs.ashbyhq.com/ramp/x") == ATSPlatform.ASHBY


def test_detect_greenhouse_from_gh_jid_query_param() -> None:
    assert (
        detect_platform("https://careers.acme.com/jobs/?gh_jid=987654")
        == ATSPlatform.GREENHOUSE
    )


def test_detect_unknown_for_unrelated_host() -> None:
    assert detect_platform("https://example.com/jobs/1") == ATSPlatform.UNKNOWN


def test_detect_unknown_for_empty_url() -> None:
    assert detect_platform("") == ATSPlatform.UNKNOWN


# --------------------------- mapper ---------------------------------------


def test_field_mapper_returns_platform_specific_names() -> None:
    gh = FieldMapper(ATSPlatform.GREENHOUSE)
    assert gh.wire_name("first_name") == "first_name"
    ashby = FieldMapper(ATSPlatform.ASHBY)
    assert ashby.wire_name("first_name") == "firstName"


def test_field_mapper_returns_none_for_unknown_platform() -> None:
    fm = FieldMapper(ATSPlatform.UNKNOWN)
    assert fm.wire_name("email") is None


def test_map_profile_splits_name_for_greenhouse() -> None:
    profile = {
        "name": "Rahul Sample",
        "email": "rahul@example.com",
        "phone": "+91-9999",
    }
    out = map_profile(profile, ATSPlatform.GREENHOUSE)
    assert out["first_name"] == "Rahul"
    assert out["last_name"] == "Sample"
    assert out["email"] == "rahul@example.com"
    assert out["phone"] == "+91-9999"


def test_map_profile_keeps_full_name_for_lever() -> None:
    profile = {"name": "Rahul Sample", "email": "rahul@example.com"}
    out = map_profile(profile, ATSPlatform.LEVER)
    # Lever schema collapses first/last into 'name'
    assert out["name"] == "Rahul Sample"


def test_map_profile_omits_missing_fields() -> None:
    profile = {"name": "Rahul"}
    out = map_profile(profile, ATSPlatform.GREENHOUSE)
    assert "phone" not in out
    assert "email" not in out


def test_map_profile_pulls_linkedin_from_urls_or_links() -> None:
    p1 = {"name": "Rahul", "urls": ["https://github.com/x", "https://linkedin.com/in/rahul"]}
    out1 = map_profile(p1, ATSPlatform.GREENHOUSE)
    assert "urls[LinkedIn]" in out1 or out1.get("urls[LinkedIn]") == "https://linkedin.com/in/rahul"

    p2 = {"name": "Rahul", "links": ["https://linkedin.com/in/rahul"]}
    out2 = map_profile(p2, ATSPlatform.ASHBY)
    assert out2.get("linkedinUrl") == "https://linkedin.com/in/rahul"


# --------------------------- prepare_package ------------------------------


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        existing = await session.get(User, user_id)
        if existing is None:
            session.add(User(id=user_id, name="Agent Test", email=f"agent-{user_id}@x.test"))


async def _seed_profile(user_id: int) -> int:
    async with session_scope() as session:
        p = Profile(
            user_id=user_id,
            source_filename="x.pdf",
            raw_resume_text="Python PostgreSQL",
            parsed_json={
                "name": "Rahul Sample",
                "email": "rahul@example.com",
                "phone": "+91-9999",
                "skills": ["Python"],
            },
        )
        session.add(p)
        await session.flush()
        return p.id


async def _seed_discovered_job(url: str = "https://jobs.lever.co/orgx/abc-123") -> int:
    async with session_scope() as session:
        dj = DiscoveredJob(
            source="lever",
            source_job_id="agent-1",
            company="OrgX",
            title="Senior Engineer",
            url=url,
            description="",
            remote=True,
        )
        session.add(dj)
        await session.flush()
        return dj.id


async def _wipe_agent_state(user_id: int) -> None:
    async with session_scope() as session:
        await session.execute(delete(Profile).where(Profile.user_id == user_id))
        await session.execute(delete(DiscoveredJob).where(DiscoveredJob.source == "lever"))


@pytest.mark.asyncio
async def test_prepare_package_with_discovered_job_pulls_fields() -> None:
    user_id = 72001
    await _ensure_user(user_id)
    await _wipe_agent_state(user_id)
    profile_id = await _seed_profile(user_id)
    job_id = await _seed_discovered_job()

    pkg = await prepare_package(profile_id=profile_id, job_id=job_id)

    assert pkg.platform == ATSPlatform.LEVER
    assert pkg.company == "OrgX"
    assert pkg.title == "Senior Engineer"
    assert pkg.applicant_fields.get("email") == "rahul@example.com"


@pytest.mark.asyncio
async def test_prepare_package_with_job_url_only() -> None:
    user_id = 72002
    await _ensure_user(user_id)
    await _wipe_agent_state(user_id)
    profile_id = await _seed_profile(user_id)

    pkg = await prepare_package(
        profile_id=profile_id,
        job_url="https://boards.greenhouse.io/stripe/jobs/123",
        company="Stripe",
        title="Engineer",
    )
    assert pkg.platform == ATSPlatform.GREENHOUSE
    assert pkg.company == "Stripe"


@pytest.mark.asyncio
async def test_prepare_package_raises_when_profile_missing() -> None:
    with pytest.raises(PackageError):
        await prepare_package(profile_id=99999, job_url="https://example.com")


@pytest.mark.asyncio
async def test_prepare_package_raises_when_neither_job_nor_url() -> None:
    user_id = 72003
    await _ensure_user(user_id)
    await _wipe_agent_state(user_id)
    profile_id = await _seed_profile(user_id)
    with pytest.raises(PackageError):
        await prepare_package(profile_id=profile_id)


@pytest.mark.asyncio
async def test_prepare_package_notes_unknown_platform() -> None:
    user_id = 72004
    await _ensure_user(user_id)
    await _wipe_agent_state(user_id)
    profile_id = await _seed_profile(user_id)
    pkg = await prepare_package(
        profile_id=profile_id, job_url="https://example.com/jobs/1"
    )
    assert pkg.platform == ATSPlatform.UNKNOWN
    assert any("ATS platform" in n for n in pkg.notes)
