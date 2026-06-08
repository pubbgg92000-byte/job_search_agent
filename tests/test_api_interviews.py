"""API tests for the Phase 3C interview prep routes.

Uses the same sync TestClient + psycopg seeding pattern as test_api_phase2b.py
to avoid asyncpg cross-loop errors.
"""
from __future__ import annotations

from collections.abc import Iterator

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
    InterviewPlan,
    InterviewQuestion,
    InterviewStudyPlan,
    Profile,
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
    with TestClient(app) as c:
        yield c


def _ensure_user(session: Session, user_id: int) -> None:
    if session.get(User, user_id) is None:
        session.add(User(id=user_id, name="API", email=f"u-{user_id}@x.test"))
        session.flush()


def _wipe(session: Session, user_id: int) -> None:
    app_ids = [
        a.id for a in session.query(Application).filter(Application.user_id == user_id).all()
    ]
    if app_ids:
        plan_ids = [
            p.id
            for p in session.query(InterviewPlan)
            .filter(InterviewPlan.application_id.in_(app_ids))
            .all()
        ]
        if plan_ids:
            session.execute(
                delete(InterviewQuestion).where(InterviewQuestion.plan_id.in_(plan_ids))
            )
            session.execute(
                delete(InterviewStudyPlan).where(InterviewStudyPlan.plan_id.in_(plan_ids))
            )
            session.execute(delete(InterviewPlan).where(InterviewPlan.id.in_(plan_ids)))
        session.execute(
            delete(ApplicationEvent).where(ApplicationEvent.application_id.in_(app_ids))
        )
        session.execute(delete(Application).where(Application.id.in_(app_ids)))
    session.execute(delete(Profile).where(Profile.user_id == user_id))


def _seed_application(
    session: Session,
    user_id: int,
    company: str = "TestCo",
    title: str = "Senior Backend Engineer",
) -> int:
    app_row = Application(
        user_id=user_id,
        company=company,
        title=title,
        url="https://test.example/job",
        source="manual",
        status="saved",
    )
    session.add(app_row)
    session.flush()
    return app_row.id


def _seed_profile(session: Session, user_id: int) -> None:
    session.add(
        Profile(
            user_id=user_id,
            source_filename="seed.pdf",
            raw_resume_text="Python PostgreSQL",
            parsed_json={
                "name": "Test",
                "email": "t@x.test",
                "skills": ["Python", "PostgreSQL", "TypeScript"],
                "experience": [{"title": "Senior Engineer", "company": "P", "bullets": []}],
            },
        )
    )


def _seed_company(session: Session, name: str = "TestCo") -> None:
    existing = session.query(CompanyProfile).filter(CompanyProfile.name == name).first()
    if existing is not None:
        return
    session.add(
        CompanyProfile(
            name=name,
            industry="fintech",
            company_size="201-500",
            funding_stage="series_b",
            remote_policy="remote_first",
            growth_score=70,
            risk_score=20,
            summary=f"{name} is a fintech company.",
            raw_signals={"phase3b": {"tech_stack": ["TypeScript", "PostgreSQL"]}},
        )
    )


USER_BASE = 87000


def _setup_user(db: Session, monkeypatch: pytest.MonkeyPatch, suffix: int) -> int:
    user_id = USER_BASE + suffix
    _ensure_user(db, user_id)
    _wipe(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    return user_id


# ---------------- plan generation ----------------


def test_post_plan_returns_dto(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 1)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()

    r = client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["application_id"] == app_id
    assert body["difficulty"] in ("easy", "medium", "hard", "very_hard")
    assert isinstance(body["stages"], list) and body["stages"]
    assert isinstance(body["technical_topics"], list)
    assert 0 <= body["confidence_score"] <= 100


def test_post_plan_400_for_unknown_application(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_user(db, monkeypatch, 2)
    r = client.post("/applications/999999/interview-prep/plan", json={})
    assert r.status_code == 404


def test_get_plan_404_when_none_yet(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 3)
    app_id = _seed_application(db, user_id)
    db.commit()
    r = client.get(f"/applications/{app_id}/interview-prep/plan")
    assert r.status_code == 404


def test_get_plan_returns_latest_after_post(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 4)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    first = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    second = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    latest = client.get(f"/applications/{app_id}/interview-prep/plan").json()
    assert latest["id"] == second["id"]
    assert latest["id"] != first["id"]


def test_list_plans_returns_count(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 5)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    r = client.get(f"/applications/{app_id}/interview-prep/plans")
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_post_plan_uses_company_profile_when_seeded(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 6)
    _seed_profile(db, user_id)
    _seed_company(db, "MidCorp")
    app_id = _seed_application(db, user_id, company="MidCorp")
    db.commit()
    body = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    joined = "\n".join(body["company_prep"])
    assert "MidCorp" in joined


# ---------------- weaknesses ----------------


def test_weaknesses_returns_report(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 7)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    r = client.get(f"/applications/{app_id}/interview-prep/weaknesses")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "strengths",
        "weaknesses",
        "matched_skills",
        "missing_skills",
        "risk_areas",
    }


def test_weaknesses_404_for_unknown_application(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_user(db, monkeypatch, 8)
    r = client.get("/applications/999999/interview-prep/weaknesses")
    assert r.status_code == 404


# ---------------- questions ----------------


def test_post_questions_populates_bank(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 9)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    r = client.post(f"/interview-plans/{plan['id']}/questions", json={})
    body = r.json()
    assert body["total"] >= 15
    assert all(q["id"] is not None for q in body["items"])


def test_list_questions_returns_persisted(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 10)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    client.post(f"/interview-plans/{plan['id']}/questions", json={})
    r = client.get(f"/interview-plans/{plan['id']}/questions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 15


def test_list_questions_filters_by_category(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 11)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    client.post(f"/interview-plans/{plan['id']}/questions", json={})
    r = client.get(f"/interview-plans/{plan['id']}/questions?category=behavioral")
    body = r.json()
    assert body["total"] >= 1
    assert all(q["category"] == "behavioral" for q in body["items"])


def test_list_questions_filters_by_difficulty(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 12)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    client.post(f"/interview-plans/{plan['id']}/questions", json={})
    r = client.get(f"/interview-plans/{plan['id']}/questions?difficulty=hard")
    body = r.json()
    assert body["total"] >= 1
    assert all(q["difficulty"] == "hard" for q in body["items"])


def test_list_questions_400_on_unknown_difficulty(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 13)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    r = client.get(f"/interview-plans/{plan['id']}/questions?difficulty=bogus")
    assert r.status_code == 400


def test_questions_404_for_unknown_plan(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_user(db, monkeypatch, 14)
    assert client.post("/interview-plans/999999/questions", json={}).status_code == 404
    assert client.get("/interview-plans/999999/questions").status_code == 404


# ---------------- study plan ----------------


def test_post_study_plan_returns_blocks(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 15)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    r = client.post(
        f"/interview-plans/{plan['id']}/study-plan",
        json={"horizon_days": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_days"] == 7
    assert len(body["blocks"]) == 8


def test_post_study_plan_400_for_unsupported_horizon(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 16)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    r = client.post(
        f"/interview-plans/{plan['id']}/study-plan",
        json={"horizon_days": 5},
    )
    assert r.status_code == 400


def test_list_study_plans_returns_all_horizons(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 17)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    for h in (1, 3, 7):
        client.post(
            f"/interview-plans/{plan['id']}/study-plan",
            json={"horizon_days": h},
        )
    r = client.get(f"/interview-plans/{plan['id']}/study-plans")
    body = r.json()
    assert body["total"] == 3
    horizons = [p["horizon_days"] for p in body["items"]]
    assert horizons == [1, 3, 7]


def test_study_plan_404_for_unknown_plan(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_user(db, monkeypatch, 18)
    r = client.post(
        "/interview-plans/999999/study-plan",
        json={"horizon_days": 7},
    )
    assert r.status_code == 404


# ---------------- get plan by id ----------------


def test_get_plan_by_id(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 19)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    plan = client.post(f"/applications/{app_id}/interview-prep/plan", json={}).json()
    r = client.get(f"/interview-plans/{plan['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == plan["id"]


def test_get_plan_by_id_404(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_user(db, monkeypatch, 20)
    assert client.get("/interview-plans/999999").status_code == 404


# ---------------- dashboard ----------------


def test_dashboard_returns_expected_payload(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 21)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    r = client.get("/interview-prep/dashboard")
    assert r.status_code == 200
    body = r.json()
    expected_keys = {
        "generated_at",
        "upcoming_interviews",
        "recent_plans",
        "risk_areas",
        "recommended_topics",
        "recommended_horizon_days",
    }
    assert expected_keys <= set(body.keys())
    assert any(p["application_id"] == app_id for p in body["recent_plans"])


def test_dashboard_upcoming_interviews_filtered_by_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 22)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    client.patch(f"/applications/{app_id}/status", json={"status": "applied"})
    client.patch(
        f"/applications/{app_id}/status", json={"status": "interview_scheduled"}
    )
    r = client.get("/interview-prep/dashboard")
    body = r.json()
    upcoming_ids = [u["application_id"] for u in body["upcoming_interviews"]]
    assert app_id in upcoming_ids


def test_dashboard_recommended_topics_aggregates_recent_plans(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 23)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    body = client.get("/interview-prep/dashboard").json()
    assert isinstance(body["recommended_topics"], list)


def test_dashboard_risk_areas_aggregates_across_plans(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _setup_user(db, monkeypatch, 24)
    _seed_profile(db, user_id)
    app_id = _seed_application(db, user_id)
    db.commit()
    client.post(f"/applications/{app_id}/interview-prep/plan", json={})
    body = client.get("/interview-prep/dashboard").json()
    assert isinstance(body["risk_areas"], list)
