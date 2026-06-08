"""Phase 2B API tests: dashboard, preferences, applications, company, skills.

Uses the sync TestClient + psycopg pattern from `test_api_jobs.py` to avoid
asyncpg cross-loop errors.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from jobforge.api.main import app
from jobforge.config import get_settings
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    CompanyProfile,
    DiscoveredJob,
    Job,
    JobMatch,
    Profile,
    TailoredArtifact,
    User,
    UserPreferences,
)


def _sync_url() -> str:
    return get_settings().database_url.replace("+asyncpg", "+psycopg")


_sync_engine = None
_SyncSession: sessionmaker[Session] | None = None


def _get_sync_session() -> sessionmaker[Session]:
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        _sync_engine = create_engine(_sync_url(), future=True)
        _SyncSession = sessionmaker(_sync_engine, expire_on_commit=False)
    return _SyncSession


@pytest.fixture
def db() -> Iterator[Session]:
    SS = _get_sync_session()
    s = SS()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _ensure_user(session: Session, user_id: int) -> None:
    if session.get(User, user_id) is None:
        session.add(User(id=user_id, name="API", email=f"u-{user_id}@x.test"))
        session.flush()


def _wipe_user(session: Session, user_id: int) -> None:
    session.execute(delete(ApplicationEvent).where(
        ApplicationEvent.application_id.in_(
            session.query(Application.id).filter(Application.user_id == user_id)
        )
    ))
    session.execute(delete(Application).where(Application.user_id == user_id))
    session.execute(delete(TailoredArtifact).where(TailoredArtifact.user_id == user_id))
    session.execute(delete(Job).where(Job.user_id == user_id))
    session.execute(delete(JobMatch).where(JobMatch.user_id == user_id))
    session.execute(delete(Profile).where(Profile.user_id == user_id))
    session.execute(delete(UserPreferences).where(UserPreferences.user_id == user_id))


def _wipe_discovery(session: Session) -> None:
    session.execute(delete(JobMatch))
    session.execute(delete(DiscoveredJob))


def _seed_profile(session: Session, user_id: int) -> int:
    p = Profile(
        user_id=user_id,
        source_filename="seed.pdf",
        raw_resume_text="Python PostgreSQL",
        parsed_json={
            "name": "Rahul Sample",
            "email": "rahul@example.com",
            "skills": ["Python", "PostgreSQL"],
            "experience": [{"title": "Senior Software Engineer", "company": "X", "bullets": []}],
        },
    )
    session.add(p)
    session.flush()
    return p.id


def _seed_jobs(session: Session, items: list[dict[str, Any]]) -> list[int]:
    ids = []
    for it in items:
        dj = DiscoveredJob(
            source=it["source"],
            source_job_id=it["source_job_id"],
            company=it["company"],
            title=it["title"],
            url=it["url"],
            location=it.get("location"),
            remote=it.get("remote", False),
            description=it.get("description", ""),
            posted_at=it.get("posted_at"),
            salary_min=it.get("salary_min"),
            salary_max=it.get("salary_max"),
            salary_currency=it.get("salary_currency"),
        )
        session.add(dj)
        session.flush()
        ids.append(dj.id)
    return ids


# --------------------------- preferences ----------------------------------


def test_get_preferences_returns_defaults_when_unset(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75001
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    r = client.get("/preferences")
    assert r.status_code == 200
    body = r.json()
    assert body["remote_only"] is True
    assert body["preferred_locations"] == []


def test_put_preferences_round_trips(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75002
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    payload = {
        "preferred_locations": ["Bengaluru"],
        "remote_only": False,
        "salary_min": 120000,
        "salary_currency": "USD",
        "excluded_companies": ["BoringCo"],
    }
    r = client.put("/preferences", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["preferred_locations"] == ["Bengaluru"]
    assert body["salary_min"] == 120000

    # Read-after-write
    r2 = client.get("/preferences")
    assert r2.json()["excluded_companies"] == ["BoringCo"]


# --------------------------- applications API -----------------------------


def test_post_application_then_patch_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75003
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    r = client.post(
        "/applications",
        json={"company": "Acme", "title": "Eng", "url": "https://x", "source": "manual"},
    )
    assert r.status_code == 200
    app_id = r.json()["id"]
    assert r.json()["status"] == "saved"

    r2 = client.patch(f"/applications/{app_id}/status", json={"status": "applied"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "applied"
    assert r2.json()["applied_at"] is not None


def test_get_application_includes_event_log(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75004
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    r = client.post(
        "/applications", json={"company": "Acme", "title": "Eng"}
    )
    app_id = r.json()["id"]
    client.patch(f"/applications/{app_id}/status", json={"status": "applied"})

    detail = client.get(f"/applications/{app_id}").json()
    assert len(detail["events"]) == 2
    assert detail["events"][0]["event_type"] == "created"
    assert detail["events"][1]["to_status"] == "applied"


def test_application_validation_400_on_missing_company(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75005
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    r = client.post("/applications", json={})
    assert r.status_code == 400


def test_applications_stats_endpoint(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75006
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    # 2 applications, one applied
    client.post("/applications", json={"company": "A", "title": "T"})
    a2 = client.post("/applications", json={"company": "B", "title": "T"}).json()
    client.patch(f"/applications/{a2['id']}/status", json={"status": "applied"})

    r = client.get("/applications/stats")
    body = r.json()
    assert body["total"] == 2
    assert body["by_status"]["applied"] == 1
    assert body["by_status"]["saved"] == 1


# --------------------------- companies ------------------------------------


def test_company_seed_then_get(client: TestClient, db: Session) -> None:
    db.execute(delete(CompanyProfile).where(CompanyProfile.name == "PutSeedCo"))
    db.commit()
    r = client.put(
        "/companies/PutSeedCo/seed",
        json={
            "industry": "fintech",
            "company_size": "51-200",
            "funding_stage": "series_b",
            "remote_policy": "remote_first",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["industry"] == "fintech"
    assert body["growth_score"] is not None
    assert body["summary"] and "PutSeedCo" in body["summary"]

    r2 = client.get("/companies/PutSeedCo")
    assert r2.status_code == 200
    assert r2.json()["funding_stage"] == "series_b"


def test_company_get_returns_null_fields_when_unknown(
    client: TestClient, db: Session
) -> None:
    db.execute(delete(CompanyProfile).where(CompanyProfile.name == "UnknownCorp"))
    db.commit()
    r = client.get("/companies/UnknownCorp")
    assert r.status_code == 200
    body = r.json()
    assert body["industry"] is None
    assert body["growth_score"] is None
    assert body["summary"] is None


# --------------------------- skills + dashboard ---------------------------


def test_skills_gaps_404_when_no_profile(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75010
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    _wipe_discovery(db)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    r = client.get("/skills/gaps")
    assert r.status_code == 404


def test_skills_gaps_returns_top_gaps_after_seed(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75011
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    _wipe_discovery(db)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    _seed_profile(db, user_id)
    fresh = datetime(2026, 6, 7, tzinfo=UTC)
    _seed_jobs(
        db,
        [
            {
                "source": "fake", "source_job_id": f"j{i}", "company": "Co",
                "title": "Senior Python Engineer",
                "description": "We use Python with Rust and Docker",
                "url": f"u{i}", "remote": True, "posted_at": fresh,
            }
            for i in range(3)
        ],
    )
    db.commit()
    r = client.get("/skills/gaps?limit_jobs=50")
    assert r.status_code == 200
    body = r.json()
    assert body["jobs_considered"] == 3
    skills = {g["skill"].lower() for g in body["top_gaps"]}
    assert "rust" in skills
    assert "docker" in skills


def test_skills_plan_includes_both_horizons(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75012
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    _wipe_discovery(db)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    _seed_profile(db, user_id)
    fresh = datetime(2026, 6, 7, tzinfo=UTC)
    _seed_jobs(
        db,
        [
            {
                "source": "fake", "source_job_id": f"p{i}", "company": "Co",
                "title": "Engineer",
                "description": "Rust Docker Kubernetes Redis Kafka Terraform AWS GCP",
                "url": f"u{i}", "remote": True, "posted_at": fresh,
            }
            for i in range(3)
        ],
    )
    db.commit()
    r = client.get("/skills/plan")
    assert r.status_code == 200
    body = r.json()
    assert body["seven_day_plan"]["horizon"] == "7-day"
    assert body["thirty_day_plan"]["horizon"] == "30-day"


def test_dashboard_returns_full_payload(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = 75020
    _ensure_user(db, user_id)
    _wipe_user(db, user_id)
    _wipe_discovery(db)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    _seed_profile(db, user_id)
    fresh = datetime.now(UTC) - timedelta(hours=2)
    _seed_jobs(
        db,
        [
            {
                "source": "f", "source_job_id": "d1", "company": "Co",
                "title": "Senior Python Engineer", "description": "Python PostgreSQL Rust",
                "url": "u", "remote": True, "posted_at": fresh,
            }
        ],
    )
    db.commit()
    # Add an application via the API.
    client.post("/applications", json={"company": "Co", "title": "Engineer"})

    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.json()
    expected_keys = {
        "jobs_found",
        "jobs_found_24h",
        "high_matches",
        "applications",
        "applications_by_status",
        "interviews",
        "offers",
        "rejections",
        "interview_rate",
        "offer_rate",
        "skill_gaps",
        "latest_sync",
        "profile_present",
    }
    assert expected_keys <= set(body.keys())
    assert body["jobs_found"] >= 1
    assert body["applications"] >= 1
    assert body["profile_present"] is True
