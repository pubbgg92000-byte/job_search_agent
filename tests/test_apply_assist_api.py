"""Apply-assist HTTP endpoints (start / get / approve / cancel / screenshot).

Uses the sync TestClient + psycopg pattern from test_api_phase2b.py to avoid
asyncpg cross-loop issues. A FakeBrowser is injected via set_browser_factory
so no Chromium is required.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from jobforge.agents_phase3.browser import BrowserAgent, NavigationResult
from jobforge.api.main import app
from jobforge.application_agent.browser import (
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    reset_registry,
)
from jobforge.applications.apply_assist import set_browser_factory
from jobforge.config import get_settings
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    ApplySession,
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


class FakeBrowser(BrowserAgent):
    def __init__(self, *, headless: bool = True) -> None:
        self.headless = headless
        self.opened: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.closed = False

    async def open(self, url: str) -> NavigationResult:
        self.opened.append(url)
        return NavigationResult(final_url=url, status_code=200, page_title="mock")

    async def fill(self, selector: str, value: str) -> None:
        self.fills.append((selector, value))

    async def click(self, selector: str) -> None:
        self.clicks.append(selector)

    async def upload(self, selector: str, file_path: str) -> None:
        self.uploads.append((selector, file_path))

    async def screenshot(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_factory_and_registry() -> Iterator[None]:
    set_browser_factory(lambda headless: FakeBrowser(headless=headless))
    reset_registry()
    yield
    set_browser_factory(None)
    reset_registry()


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
        session.add(User(id=user_id, name="API", email=f"aa-{user_id}@x.test"))
        session.flush()


def _wipe_user(session: Session, user_id: int) -> None:
    session.execute(
        delete(ApplySession).where(
            ApplySession.application_id.in_(
                session.query(Application.id).filter(Application.user_id == user_id)
            )
        )
    )
    session.execute(
        delete(ApplicationEvent).where(
            ApplicationEvent.application_id.in_(
                session.query(Application.id).filter(Application.user_id == user_id)
            )
        )
    )
    session.execute(delete(Application).where(Application.user_id == user_id))
    session.execute(delete(Profile).where(Profile.user_id == user_id))


def _seed_profile(session: Session, user_id: int) -> int:
    p = Profile(
        user_id=user_id,
        source_filename="seed.pdf",
        raw_resume_text="Python",
        parsed_json={"name": "Rahul Sample", "email": "rahul@example.com", "phone": "+1-555"},
    )
    session.add(p)
    session.flush()
    return p.id


def _seed_application(session: Session, user_id: int, *, url: str) -> int:
    a = Application(
        user_id=user_id,
        company="Stripe",
        title="Engineer",
        url=url,
        status="saved",
    )
    session.add(a)
    session.flush()
    return a.id


GREENHOUSE_URL = "https://boards.greenhouse.io/stripe/jobs/123"


def test_start_returns_ready_for_review_after_form_fill(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()

    r = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["state"] == STATE_READY_FOR_REVIEW
    assert body["session"]["platform"] == "greenhouse"
    assert body["session"]["screenshot_count"] >= 1
    types = [e["event_type"] for e in body["events"]]
    assert "apply_assist.form_started" in types
    assert "apply_assist.ready_for_review" in types


def test_start_404_for_missing_application(db: Session, client: TestClient) -> None:
    r = client.post("/applications/99999999/apply-assist/start", json={})
    assert r.status_code == 404


def test_start_400_when_application_has_no_url(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    a = Application(user_id=settings.sole_user_id, company="X", title="Y", url=None, status="saved")
    db.add(a)
    db.flush()
    db.commit()
    r = client.post(f"/applications/{a.id}/apply-assist/start", json={})
    assert r.status_code == 400
    assert "url" in r.json()["detail"].lower()


def test_start_400_when_no_profile_uploaded(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    assert r.status_code == 400
    assert "profile" in r.json()["detail"].lower()


def test_start_409_when_concurrency_cap_exceeded(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    a1 = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    a2 = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()

    r1 = client.post(f"/applications/{a1}/apply-assist/start", json={})
    assert r1.status_code == 200
    # Default max_concurrent=1; second start while first sits at READY rejects.
    r2 = client.post(f"/applications/{a2}/apply-assist/start", json={})
    assert r2.status_code == 409


def test_get_session_404_for_unknown_id(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r = client.get(f"/applications/{app_id}/apply-assist/sessions/9999")
    assert r.status_code == 404


def test_get_session_echoes_state(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    r2 = client.get(f"/applications/{app_id}/apply-assist/sessions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session"]["id"] == sid


def test_approve_advances_application_to_applied(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]

    r2 = client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/approve")
    assert r2.status_code == 200
    body = r2.json()
    assert body["session"]["state"] == STATE_SUBMITTED
    assert body["application_status"] == "applied"

    # Verify the application row actually transitioned.
    r3 = client.get(f"/applications/{app_id}")
    assert r3.json()["status"] == "applied"


def test_approve_409_when_session_not_ready(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    # First approve flips state to submitted; second approve must 409.
    client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/approve")
    r2 = client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/approve")
    assert r2.status_code == 409


def test_cancel_marks_session_cancelled(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    r2 = client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/cancel")
    assert r2.status_code == 200
    assert r2.json()["session"]["state"] == "cancelled"


def test_cancel_after_submit_is_idempotent_no_op(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/approve")
    r2 = client.post(f"/applications/{app_id}/apply-assist/sessions/{sid}/cancel")
    assert r2.status_code == 200
    assert r2.json()["session"]["state"] == STATE_SUBMITTED  # cancel was a no-op


def test_screenshot_endpoint_serves_png(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    r2 = client.get(f"/applications/{app_id}/apply-assist/sessions/{sid}/screenshot/0")
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("image/png")
    assert r2.content[:4] == b"\x89PNG"


def test_screenshot_404_for_out_of_range(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    app_id = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{app_id}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    r2 = client.get(f"/applications/{app_id}/apply-assist/sessions/{sid}/screenshot/999")
    assert r2.status_code == 404


def test_session_404_when_application_id_mismatched(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    a1 = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    a2 = _seed_application(db, settings.sole_user_id, url=GREENHOUSE_URL)
    db.commit()
    r1 = client.post(f"/applications/{a1}/apply-assist/start", json={})
    sid = r1.json()["session"]["id"]
    # Fetch session via a different application_id — must 404.
    r2 = client.get(f"/applications/{a2}/apply-assist/sessions/{sid}")
    assert r2.status_code == 404


def test_unknown_platform_url_fails_start_with_400(db: Session, client: TestClient) -> None:
    settings = get_settings()
    _ensure_user(db, settings.sole_user_id)
    _wipe_user(db, settings.sole_user_id)
    _seed_profile(db, settings.sole_user_id)
    a = Application(
        user_id=settings.sole_user_id,
        company="X",
        title="Y",
        url="https://example.com/jobs/1",
        status="saved",
    )
    db.add(a)
    db.flush()
    db.commit()
    r = client.post(f"/applications/{a.id}/apply-assist/start", json={})
    assert r.status_code == 400
    assert "unknown" in r.json()["detail"].lower() or "ats" in r.json()["detail"].lower()
