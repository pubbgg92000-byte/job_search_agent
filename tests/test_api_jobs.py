"""Tests for the Phase 2 /jobs API endpoints.

These tests run synchronously because FastAPI's TestClient is sync. To seed
the DB we use a sync SQLAlchemy engine pointed at the same Postgres — keeping
the test body and the request handler in separate event loops avoids the
asyncpg cross-loop issue.
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
    DiscoveredJob,
    Job,
    JobMatch,
    Profile,
    TailoredArtifact,
    User,
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
    """One TestClient per test so anyio's portal/loop is scoped properly.

    Without `with`, each request opens a fresh loop and asyncpg connections
    leak across loops — pinning a single loop per test fixes the cross-loop
    `Task ... attached to a different loop` error.
    """
    with TestClient(app) as c:
        yield c


def _seed_discovered_jobs(session: Session, jobs: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for j in jobs:
        row = DiscoveredJob(
            source=j["source"],
            source_job_id=j["source_job_id"],
            company=j["company"],
            title=j["title"],
            location=j.get("location"),
            remote=j.get("remote", False),
            description=j.get("description", ""),
            url=j["url"],
            posted_at=j.get("posted_at"),
            salary_min=j.get("salary_min"),
            salary_max=j.get("salary_max"),
            salary_currency=j.get("salary_currency"),
        )
        session.add(row)
        session.flush()
        ids.append(row.id)
    return ids


def _ensure_user_and_profile(session: Session, user_id: int) -> int:
    user = session.get(User, user_id)
    if user is None:
        session.add(User(id=user_id, name="API Test", email=f"apitest-{user_id}@x.test"))
    profile = Profile(
        user_id=user_id,
        source_filename="seed.pdf",
        raw_resume_text="Python PostgreSQL",
        parsed_json={
            "skills": ["Python", "PostgreSQL"],
            "experience": [
                {"title": "Senior Software Engineer", "company": "X", "bullets": []}
            ],
        },
    )
    session.add(profile)
    session.flush()
    return profile.id


def _wipe_discovery(session: Session) -> None:
    session.execute(delete(JobMatch))
    session.execute(delete(DiscoveredJob))


def _wipe_user_data(session: Session, user_id: int) -> None:
    session.execute(delete(Application).where(Application.user_id == user_id))
    session.execute(delete(TailoredArtifact).where(TailoredArtifact.user_id == user_id))
    session.execute(delete(Job).where(Job.user_id == user_id))
    session.execute(delete(JobMatch).where(JobMatch.user_id == user_id))
    session.execute(delete(Profile).where(Profile.user_id == user_id))


# ---------------------------- tests ----------------------------


def test_list_jobs_returns_empty_when_no_data(db: Session, client: TestClient) -> None:
    _wipe_discovery(db)
    db.commit()
    r = client.get("/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body == {"total": 0, "limit": 20, "offset": 0, "items": []}


def test_list_jobs_paginates_and_returns_total(db: Session, client: TestClient) -> None:
    _wipe_discovery(db)
    _seed_discovered_jobs(
        db,
        [
            {
                "source": "fake",
                "source_job_id": f"j{i}",
                "company": "Co",
                "title": f"Role {i}",
                "url": f"https://example.com/{i}",
                "posted_at": datetime(2026, 6, 1, tzinfo=UTC) + timedelta(days=i),
            }
            for i in range(5)
        ],
    )
    db.commit()

    r = client.get("/jobs?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_list_jobs_filters_by_source_and_remote(db: Session, client: TestClient) -> None:
    _wipe_discovery(db)
    _seed_discovered_jobs(
        db,
        [
            {"source": "greenhouse", "source_job_id": "g1", "company": "A", "title": "T", "url": "u1", "remote": True},
            {"source": "greenhouse", "source_job_id": "g2", "company": "A", "title": "T", "url": "u2", "remote": False},
            {"source": "lever", "source_job_id": "l1", "company": "B", "title": "T", "url": "u3", "remote": True},
        ],
    )
    db.commit()

    assert client.get("/jobs?source=greenhouse").json()["total"] == 2
    assert client.get("/jobs?remote=true").json()["total"] == 2
    assert client.get("/jobs?source=greenhouse&remote=false").json()["total"] == 1


def test_list_jobs_sorts_by_posted_at_desc_by_default(db: Session, client: TestClient) -> None:
    _wipe_discovery(db)
    _seed_discovered_jobs(
        db,
        [
            {"source": "f", "source_job_id": "a", "company": "Co", "title": "A", "url": "u1", "posted_at": datetime(2026, 6, 1, tzinfo=UTC)},
            {"source": "f", "source_job_id": "b", "company": "Co", "title": "B", "url": "u2", "posted_at": datetime(2026, 6, 5, tzinfo=UTC)},
            {"source": "f", "source_job_id": "c", "company": "Co", "title": "C", "url": "u3", "posted_at": datetime(2026, 6, 3, tzinfo=UTC)},
        ],
    )
    db.commit()
    titles = [item["title"] for item in client.get("/jobs").json()["items"]]
    assert titles == ["B", "C", "A"]


def test_get_job_returns_detail(db: Session, client: TestClient) -> None:
    _wipe_discovery(db)
    ids = _seed_discovered_jobs(
        db,
        [
            {
                "source": "fake",
                "source_job_id": "j1",
                "company": "Co",
                "title": "T",
                "url": "https://x",
                "description": "long description",
            }
        ],
    )
    db.commit()
    r = client.get(f"/jobs/{ids[0]}")
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == "long description"
    assert "first_seen_at" in body


def test_get_job_404_when_missing(client: TestClient) -> None:
    r = client.get("/jobs/999999")
    assert r.status_code == 404


def test_get_match_404_when_no_profile(db: Session, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _wipe_discovery(db)
    user_id = 80001
    _wipe_user_data(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)

    ids = _seed_discovered_jobs(
        db, [{"source": "f", "source_job_id": "j1", "company": "Co", "title": "T", "url": "u"}]
    )
    db.commit()
    r = client.get(f"/jobs/{ids[0]}/match")
    assert r.status_code == 404
    assert "profile" in r.json()["detail"].lower()


def test_top_matches_ranks_jobs_by_score(db: Session, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _wipe_discovery(db)
    user_id = 80002
    _wipe_user_data(db, user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    _ensure_user_and_profile(db, user_id)
    fresh = datetime(2026, 6, 7, tzinfo=UTC)
    _seed_discovered_jobs(
        db,
        [
            {
                "source": "f", "source_job_id": "good", "company": "Co",
                "title": "Senior Python Engineer", "description": "Python PostgreSQL",
                "remote": True, "url": "u1", "posted_at": fresh,
            },
            {
                "source": "f", "source_job_id": "bad", "company": "Co",
                "title": "Junior PHP Wrangler", "description": "PHP Wordpress",
                "remote": False, "url": "u2",
                "posted_at": datetime(2025, 1, 1, tzinfo=UTC),
            },
        ],
    )
    db.commit()

    r = client.get("/jobs/top-matches?limit=2&min_score=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["job"]["source_job_id"] == "good"
    assert body[0]["match"]["score"] >= body[1]["match"]["score"]


def test_get_match_returns_full_breakdown(db: Session, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _wipe_discovery(db)
    user_id = 80003
    _wipe_user_data(db, user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    profile_id = _ensure_user_and_profile(db, user_id)
    ids = _seed_discovered_jobs(
        db,
        [
            {
                "source": "f", "source_job_id": "x", "company": "Co",
                "title": "Senior Python Engineer", "description": "Python PostgreSQL",
                "remote": True, "url": "u",
                "posted_at": datetime(2026, 6, 7, tzinfo=UTC),
            }
        ],
    )
    db.commit()

    r = client.get(f"/jobs/{ids[0]}/match")
    assert r.status_code == 200
    body = r.json()
    assert body["profile_id"] == profile_id
    for axis in ("skill_match", "seniority_match", "location_match", "remote_match", "salary_match", "freshness"):
        assert 0 <= body[axis] <= 100
    assert 0 <= body["score"] <= 100


def test_post_sync_with_no_sources_returns_empty_runs(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from jobforge.api.routes import jobs as jobs_route

    async def fake_sync_all():
        return []

    monkeypatch.setattr(jobs_route, "sync_all_sources", fake_sync_all)
    r = client.post("/jobs/sync")
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_post_sync_returns_per_source_results(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from jobforge.api.routes import jobs as jobs_route
    from jobforge.discovery.service import SyncRunResult

    async def fake_sync_all():
        return [
            SyncRunResult("greenhouse", 1, 5, 5, 0, 0, "ok"),
            SyncRunResult("lever", 2, 0, 0, 0, 0, "error", error="boom"),
        ]

    monkeypatch.setattr(jobs_route, "sync_all_sources", fake_sync_all)
    r = client.post("/jobs/sync")
    body = r.json()
    assert {x["source"] for x in body["runs"]} == {"greenhouse", "lever"}
    err = next(x for x in body["runs"] if x["source"] == "lever")
    assert err["status"] == "error"
    assert err["error"] == "boom"
