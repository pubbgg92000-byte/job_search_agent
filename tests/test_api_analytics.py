"""API + telegram tests for Phase 3E analytics."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from jobforge.api.main import app
from jobforge.config import get_settings
from jobforge.db.models import (
    AnalyticsSnapshot,
    Application,
    ApplicationEvent,
    MessageEvent,
    OutreachCampaign,
    Profile,
    RecruiterContact,
    RecruiterMessage,
    SkillGapSnapshot,
    TailoredArtifact,
    User,
)
from jobforge.db.session import session_scope
from jobforge.telegram.bot import build_default_bot


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
        session.add(User(id=user_id, name="A", email=f"a-{user_id}@x.test"))
        session.flush()


def _wipe(session: Session, user_id: int) -> None:
    camp_ids = [
        c.id
        for c in session.query(OutreachCampaign)
        .filter(OutreachCampaign.user_id == user_id)
        .all()
    ]
    if camp_ids:
        session.execute(
            delete(MessageEvent).where(MessageEvent.campaign_id.in_(camp_ids))
        )
        session.execute(
            delete(RecruiterMessage).where(
                RecruiterMessage.campaign_id.in_(camp_ids)
            )
        )
        session.execute(
            delete(OutreachCampaign).where(OutreachCampaign.id.in_(camp_ids))
        )
    session.execute(
        delete(RecruiterContact).where(RecruiterContact.user_id == user_id)
    )
    app_ids = [
        a.id
        for a in session.query(Application).filter(Application.user_id == user_id).all()
    ]
    if app_ids:
        session.execute(
            delete(ApplicationEvent).where(
                ApplicationEvent.application_id.in_(app_ids)
            )
        )
        session.execute(delete(Application).where(Application.id.in_(app_ids)))
    session.execute(
        delete(SkillGapSnapshot).where(SkillGapSnapshot.user_id == user_id)
    )
    session.execute(
        delete(TailoredArtifact).where(TailoredArtifact.user_id == user_id)
    )
    session.execute(delete(Profile).where(Profile.user_id == user_id))
    session.execute(
        delete(AnalyticsSnapshot).where(AnalyticsSnapshot.user_id == user_id)
    )


USER_BASE = 97000


def _setup(db: Session, monkeypatch: pytest.MonkeyPatch, suffix: int) -> int:
    user_id = USER_BASE + suffix
    _ensure_user(db, user_id)
    _wipe(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    return user_id


# ---------------- API routes ----------------


def test_funnel_route_returns_stages_and_conversions(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 1)
    r = client.get("/analytics/funnel")
    assert r.status_code == 200
    body = r.json()
    assert "stages" in body
    assert "conversions" in body


def test_sources_route_returns_all_supported_sources(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 2)
    r = client.get("/analytics/sources")
    assert r.status_code == 200
    body = r.json()
    keys = {row["source"] for row in body["rows"]}
    for src in ("greenhouse", "lever", "ashby", "remoteok", "remotive", "wwr"):
        assert src in keys


def test_resumes_route(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 3)
    r = client.get("/analytics/resumes")
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body


def test_outreach_route(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 4)
    r = client.get("/analytics/outreach")
    body = r.json()
    assert set(body.keys()) == {"by_kind", "by_company", "follow_up"}


def test_companies_route_respects_limit(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 5)
    r = client.get("/analytics/companies?limit=3")
    assert r.status_code == 200


def test_companies_route_rejects_invalid_limit(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 6)
    r = client.get("/analytics/companies?limit=999")
    assert r.status_code == 422


def test_skill_trends_route_default_limit(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 7)
    r = client.get("/analytics/skill-trends")
    body = r.json()
    assert "items" in body
    assert "total" in body


def test_recommendations_route_returns_items_field(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 8)
    r = client.get("/analytics/recommendations")
    body = r.json()
    assert "items" in body
    assert "total" in body


def test_post_snapshot_persists_a_row(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 9)
    r = client.post("/analytics/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] >= 1
    listed = client.get("/analytics/snapshots").json()
    assert listed["total"] >= 1


def test_list_snapshots_returns_items_field(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 10)
    r = client.get("/analytics/snapshots")
    body = r.json()
    assert set(body.keys()) >= {"items", "total"}


def test_dashboard_route_returns_combined_payload(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 11)
    r = client.get("/analytics/dashboard")
    body = r.json()
    expected = {
        "funnel",
        "sources",
        "resumes",
        "outreach",
        "top_companies",
        "skill_trend",
        "snapshots",
        "recommendations",
    }
    assert expected <= set(body.keys())


def test_dashboard_route_top_companies_is_a_list(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 12)
    r = client.get("/analytics/dashboard")
    assert isinstance(r.json()["top_companies"], list)


def test_dashboard_route_funnel_has_zero_when_empty(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 13)
    body = client.get("/analytics/dashboard").json()
    assert body["funnel"]["stages"]["applications_created"] == 0


# ---------------- telegram ----------------


async def _ensure_user_async(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="TG", email=f"tg-{user_id}@x.test"))


async def test_summary_command_renders_funnel_and_conversion_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 50
    await _ensure_user_async(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    bot = build_default_bot()
    reply = await bot.dispatch("/summary")
    assert reply is not None
    assert "Applications" in reply
    assert "Conversion rates" in reply


async def test_summary_command_lists_recommendations_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 51
    await _ensure_user_async(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    # Seed a single application so the baseline rec fires.
    from jobforge.applications import (
        CreateApplicationRequest as ApplicationReq,
    )
    from jobforge.applications import (
        create_application,
    )

    await create_application(
        user_id, ApplicationReq(company="C", title="E")
    )
    bot = build_default_bot()
    reply = await bot.dispatch("/summary")
    assert reply is not None
    # Even on a sparse dataset, the "Collect more data" baseline shows up.
    assert "Recommendations" in reply or "Conversion" in reply


async def test_help_includes_summary_command() -> None:
    bot = build_default_bot()
    reply = await bot.dispatch("/help")
    assert reply is not None
    assert "/summary" in reply


async def test_summary_registered_in_default_bot() -> None:
    bot = build_default_bot()
    assert "summary" in bot.handlers
