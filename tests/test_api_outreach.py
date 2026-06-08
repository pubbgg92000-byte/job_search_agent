"""API tests for the Phase 3D outreach routes.

Uses the sync TestClient + psycopg pattern from `test_api_phase2b.py` to
avoid asyncpg cross-loop errors.
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
    MessageEvent,
    OutreachCampaign,
    Profile,
    RecruiterContact,
    RecruiterMessage,
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
        session.add(User(id=user_id, name="API-out", email=f"o-{user_id}@x.test"))
        session.flush()


def _wipe(session: Session, user_id: int) -> None:
    campaign_ids = [
        c.id
        for c in session.query(OutreachCampaign)
        .filter(OutreachCampaign.user_id == user_id)
        .all()
    ]
    if campaign_ids:
        session.execute(
            delete(MessageEvent).where(MessageEvent.campaign_id.in_(campaign_ids))
        )
        session.execute(
            delete(RecruiterMessage).where(
                RecruiterMessage.campaign_id.in_(campaign_ids)
            )
        )
        session.execute(
            delete(OutreachCampaign).where(OutreachCampaign.id.in_(campaign_ids))
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
    session.execute(delete(Profile).where(Profile.user_id == user_id))


def _seed_profile(session: Session, user_id: int) -> None:
    session.add(
        Profile(
            user_id=user_id,
            source_filename="seed.pdf",
            raw_resume_text="Python",
            parsed_json={
                "name": "Rahul",
                "email": "rahul@x.test",
                "skills": ["Python", "PostgreSQL", "TypeScript"],
                "experience": [
                    {"title": "Senior Engineer", "company": "Past", "bullets": []}
                ],
            },
        )
    )


USER_BASE = 92000


def _setup(db: Session, monkeypatch: pytest.MonkeyPatch, suffix: int) -> int:
    user_id = USER_BASE + suffix
    _ensure_user(db, user_id)
    _wipe(db, user_id)
    db.commit()
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    return user_id


# ---------------- contacts API ----------------


def test_post_contact_returns_dto(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 1)
    r = client.post(
        "/outreach/contacts",
        json={
            "company": "Acme",
            "name": "Sam Tan",
            "kind": "recruiter",
            "linkedin_url": "https://linkedin.com/in/samtan",
            "source": "manual",
            "confidence": 80,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["company"] == "Acme"
    assert body["name"] == "Sam Tan"
    assert body["id"] >= 1


def test_post_contact_400_on_invalid_kind(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 2)
    r = client.post(
        "/outreach/contacts",
        json={"company": "Acme", "name": "Sam", "kind": "ceo"},
    )
    assert r.status_code == 400


def test_post_contact_idempotent_for_same_normalized_name(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 3)
    a = client.post(
        "/outreach/contacts", json={"company": "Acme", "name": "Sam Tan"}
    ).json()
    b = client.post(
        "/outreach/contacts",
        json={"company": "Acme", "name": "sam tan", "role": "Senior Recruiter"},
    ).json()
    assert a["id"] == b["id"]
    assert b["role"] == "Senior Recruiter"


def test_list_contacts_filters_by_kind(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 4)
    client.post(
        "/outreach/contacts",
        json={"company": "Acme", "name": "R1", "kind": "recruiter"},
    )
    client.post(
        "/outreach/contacts",
        json={"company": "Acme", "name": "HM1", "kind": "hiring_manager"},
    )
    r = client.get("/outreach/contacts?kind=hiring_manager")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "HM1"


def test_list_contacts_rejects_unknown_kind_filter(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 5)
    r = client.get("/outreach/contacts?kind=ceo")
    assert r.status_code == 400


def test_get_contact_returns_404(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 6)
    assert client.get("/outreach/contacts/999999").status_code == 404


def test_delete_contact_removes_row(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 7)
    c = client.post(
        "/outreach/contacts", json={"company": "Acme", "name": "Sam"}
    ).json()
    r = client.delete(f"/outreach/contacts/{c['id']}")
    assert r.status_code == 200
    assert client.get(f"/outreach/contacts/{c['id']}").status_code == 404


def test_discover_contacts_with_seeds(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 8)
    r = client.post(
        "/outreach/contacts/discover",
        json={
            "company": "Acme",
            "seeds": [
                {"company": "Acme", "name": "Asha Mehta", "kind": "talent_partner"},
                {"company": "Acme", "name": "Ben Lee", "kind": "hiring_manager"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2


def test_discover_contacts_400_for_missing_company(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 9)
    r = client.post("/outreach/contacts/discover", json={"company": ""})
    assert r.status_code == 400


# ---------------- campaigns API ----------------


def _seed_contact_via_api(client: TestClient) -> int:
    return client.post(
        "/outreach/contacts",
        json={"company": "Acme", "name": "Sam"},
    ).json()["id"]


def test_post_campaign_returns_dto(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 10)
    cid = _seed_contact_via_api(client)
    r = client.post(
        "/outreach/campaigns",
        json={"contact_id": cid, "goal": "initial_outreach"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "drafted"


def test_post_campaign_404_for_unknown_contact(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 11)
    r = client.post(
        "/outreach/campaigns",
        json={"contact_id": 999999, "goal": "initial_outreach"},
    )
    assert r.status_code == 404


def test_post_campaign_400_for_invalid_goal(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 12)
    cid = _seed_contact_via_api(client)
    r = client.post(
        "/outreach/campaigns",
        json={"contact_id": cid, "goal": "world_domination"},
    )
    assert r.status_code == 400


def test_list_campaigns_filters_by_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 13)
    cid = _seed_contact_via_api(client)
    a = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    b = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    client.patch(f"/outreach/campaigns/{b['id']}/status", json={"status": "sent"})
    r = client.get("/outreach/campaigns?status=drafted")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == a["id"]


def test_list_campaigns_rejects_unknown_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 14)
    r = client.get("/outreach/campaigns?status=ghosted")
    assert r.status_code == 400


def test_get_campaign_includes_events_and_messages(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 15)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    client.post(
        f"/outreach/campaigns/{camp['id']}/messages",
        json={"kind": "initial_outreach", "role_title": "Engineer"},
    )
    body = client.get(f"/outreach/campaigns/{camp['id']}").json()
    assert "events" in body and len(body["events"]) >= 2
    assert "messages" in body and len(body["messages"]) == 1


def test_get_campaign_returns_404(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 16)
    assert client.get("/outreach/campaigns/999999").status_code == 404


def test_patch_status_advances_and_logs(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 17)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    r = client.patch(
        f"/outreach/campaigns/{camp['id']}/status",
        json={"status": "sent"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


def test_patch_status_rejects_invalid_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 18)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    r = client.patch(
        f"/outreach/campaigns/{camp['id']}/status",
        json={"status": "ghosted"},
    )
    assert r.status_code == 400


# ---------------- messages API ----------------


def test_post_message_uses_campaign_contact_when_payload_blank(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 19)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    r = client.post(
        f"/outreach/campaigns/{camp['id']}/messages",
        json={"kind": "initial_outreach", "role_title": "Engineer"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["body"]
    assert "Acme" in body["body"]
    assert "Sam" in body["body"]


def test_post_message_400_on_unknown_kind(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 20)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    r = client.post(
        f"/outreach/campaigns/{camp['id']}/messages",
        json={"kind": "rude_demand"},
    )
    assert r.status_code == 400


def test_post_message_404_for_unknown_campaign(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 21)
    r = client.post(
        "/outreach/campaigns/999999/messages",
        json={"kind": "initial_outreach", "company": "X", "contact_name": "X"},
    )
    assert r.status_code == 404


def test_preview_message_returns_draft_without_persisting(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 22)
    _seed_profile(db, USER_BASE + 22)
    db.commit()
    r = client.post(
        "/outreach/messages/preview",
        json={
            "kind": "initial_outreach",
            "company": "Acme",
            "contact_name": "Sam",
            "role_title": "Engineer",
        },
    )
    assert r.status_code == 200
    assert "Acme" in r.json()["body"]


def test_preview_message_400_on_missing_company(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 23)
    r = client.post(
        "/outreach/messages/preview",
        json={"kind": "initial_outreach", "contact_name": "Sam"},
    )
    assert r.status_code == 400


def test_mark_sent_advances_status(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 24)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    msg = client.post(
        f"/outreach/campaigns/{camp['id']}/messages",
        json={"kind": "initial_outreach", "role_title": "Engineer"},
    ).json()
    r = client.post(
        f"/outreach/campaigns/{camp['id']}/messages/{msg['id']}/sent",
        json={"follow_up_in_days": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert body["follow_up_due_at"] is not None


def test_mark_sent_404_for_unknown_campaign(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 25)
    r = client.post(
        "/outreach/campaigns/999999/messages/1/sent", json={"follow_up_in_days": 0}
    )
    assert r.status_code == 404


# ---------------- dashboard / metrics / replies ----------------


def test_dashboard_returns_expected_keys(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 26)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    client.patch(
        f"/outreach/campaigns/{camp['id']}/status", json={"status": "sent"}
    )
    r = client.get("/outreach/dashboard")
    body = r.json()
    expected = {
        "metrics",
        "due_follow_ups",
        "recent_replies",
        "recent_contacts",
        "recent_campaigns",
    }
    assert expected <= set(body.keys())


def test_metrics_route(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 27)
    r = client.get("/outreach/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "response_rate" in body


def test_replies_route_returns_recent(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 28)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    client.patch(
        f"/outreach/campaigns/{camp['id']}/status", json={"status": "sent"}
    )
    client.patch(
        f"/outreach/campaigns/{camp['id']}/status", json={"status": "replied"}
    )
    body = client.get("/outreach/replies").json()
    assert body["total"] >= 1


def test_follow_ups_route_lists_overdue(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db, monkeypatch, 29)
    cid = _seed_contact_via_api(client)
    camp = client.post("/outreach/campaigns", json={"contact_id": cid}).json()
    msg = client.post(
        f"/outreach/campaigns/{camp['id']}/messages",
        json={"kind": "initial_outreach", "role_title": "Engineer"},
    ).json()
    # mark sent with 0 days follow-up — follow_up_due_at stays null, NOT due
    client.post(
        f"/outreach/campaigns/{camp['id']}/messages/{msg['id']}/sent",
        json={"follow_up_in_days": 0},
    )
    body = client.get("/outreach/follow-ups").json()
    # The endpoint returns due rows; with 0-day plan there should be none from this campaign.
    assert all(c["id"] != camp["id"] for c in body["items"])
