"""Tests for the application tracking service (status flow + event log + stats)."""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from jobforge.applications import (
    ApplicationError,
    CreateApplicationRequest,
    StatusUpdateRequest,
    create_application,
    get_application,
    list_applications,
    list_events,
    stats,
    update_status,
)
from jobforge.applications.status import (
    ALL_STATUSES,
    STATUS_APPLIED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_SAVED,
    STATUS_TAILORED,
    is_forward_transition,
    is_terminal,
    is_valid_status,
)
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    DiscoveredJob,
    User,
)
from jobforge.db.session import session_scope


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        existing = await session.get(User, user_id)
        if existing is None:
            session.add(User(id=user_id, name="App Test", email=f"app-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        # Cascade from applications will hit events; ensure clean slate.
        ids = (
            await session.execute(
                Application.__table__.select().where(Application.user_id == user_id)
            )
        ).all()
        app_ids = [row.id for row in ids]
        if app_ids:
            await session.execute(
                delete(ApplicationEvent).where(
                    ApplicationEvent.application_id.in_(app_ids)
                )
            )
            await session.execute(
                delete(Application).where(Application.id.in_(app_ids))
            )


# --------------------------- status module --------------------------------


def test_is_valid_status_recognizes_all_statuses() -> None:
    for s in ALL_STATUSES:
        assert is_valid_status(s)
    assert is_valid_status("not-a-status") is False


def test_is_forward_transition_allows_saved_to_applied() -> None:
    assert is_forward_transition(STATUS_SAVED, STATUS_APPLIED) is True


def test_is_forward_transition_rejects_backwards_jump() -> None:
    assert is_forward_transition(STATUS_OFFER, STATUS_APPLIED) is False


def test_is_terminal_for_rejected_and_accepted() -> None:
    assert is_terminal(STATUS_REJECTED) is True
    assert is_terminal("accepted") is True
    assert is_terminal(STATUS_APPLIED) is False


# --------------------------- service --------------------------------------


async def test_create_application_records_created_event() -> None:
    user_id = 71001
    await _ensure_user(user_id)
    await _wipe(user_id)

    row = await create_application(
        user_id,
        CreateApplicationRequest(
            company="Acme",
            title="Backend Engineer",
            url="https://example.com/jobs/1",
            source="manual",
        ),
    )
    assert row.id > 0
    assert row.status == STATUS_SAVED
    events = await list_events(row.id)
    assert len(events) == 1
    assert events[0].event_type == "created"
    assert events[0].to_status == STATUS_SAVED


async def test_create_rejects_invalid_status() -> None:
    with pytest.raises(ApplicationError):
        await create_application(
            71001,
            CreateApplicationRequest(
                company="Acme", title="Eng", status="not-a-real-status"
            ),
        )


async def test_create_requires_company_and_title() -> None:
    with pytest.raises(ApplicationError):
        await create_application(
            71001,
            CreateApplicationRequest(company="", title=""),
        )


async def test_create_hydrates_from_discovered_job() -> None:
    user_id = 71002
    await _ensure_user(user_id)
    await _wipe(user_id)
    async with session_scope() as session:
        dj = DiscoveredJob(
            source="fake",
            source_job_id="dj-1",
            company="DiscoveredCo",
            title="Senior Engineer",
            url="https://example.com/discovered/1",
            description="",
            remote=True,
        )
        session.add(dj)
        await session.flush()
        dj_id = dj.id

    row = await create_application(
        user_id,
        CreateApplicationRequest(
            company="",  # let hydration fill it in
            title="",
            discovered_job_id=dj_id,
        ),
    )
    assert row.company == "DiscoveredCo"
    assert row.title == "Senior Engineer"
    assert row.url == "https://example.com/discovered/1"
    assert row.discovered_job_id == dj_id


async def test_status_change_appends_event_and_updates_row() -> None:
    user_id = 71003
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )

    updated = await update_status(
        user_id, row.id, StatusUpdateRequest(to_status=STATUS_APPLIED, notes="sent")
    )
    assert updated.status == STATUS_APPLIED
    assert updated.applied_at is not None

    events = await list_events(row.id)
    assert [e.event_type for e in events] == ["created", "status_change"]
    assert events[1].from_status == STATUS_SAVED
    assert events[1].to_status == STATUS_APPLIED
    assert events[1].notes == "sent"


async def test_status_change_marks_unusual_for_backwards_jump() -> None:
    user_id = 71004
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    await update_status(user_id, row.id, StatusUpdateRequest(to_status=STATUS_APPLIED))
    await update_status(user_id, row.id, StatusUpdateRequest(to_status=STATUS_SAVED))

    events = await list_events(row.id)
    last = events[-1]
    assert last.event_type == "status_change_unusual"
    assert last.from_status == STATUS_APPLIED
    assert last.to_status == STATUS_SAVED


async def test_update_status_noop_when_same_status() -> None:
    user_id = 71005
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    await update_status(user_id, row.id, StatusUpdateRequest(to_status=STATUS_SAVED))
    events = await list_events(row.id)
    assert len(events) == 1  # only the create event


async def test_update_status_404_on_wrong_user() -> None:
    user_id = 71006
    other_user = 71007
    await _ensure_user(user_id)
    await _ensure_user(other_user)
    await _wipe(user_id)
    row = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    with pytest.raises(ApplicationError):
        await update_status(
            other_user, row.id, StatusUpdateRequest(to_status=STATUS_APPLIED)
        )


async def test_list_filters_by_status() -> None:
    user_id = 71008
    await _ensure_user(user_id)
    await _wipe(user_id)
    r1 = await create_application(
        user_id, CreateApplicationRequest(company="A", title="T")
    )
    assert r1.id > 0
    r2 = await create_application(
        user_id, CreateApplicationRequest(company="B", title="T")
    )
    await update_status(user_id, r2.id, StatusUpdateRequest(to_status=STATUS_APPLIED))

    total_all, _ = await list_applications(user_id)
    total_applied, applied = await list_applications(user_id, status=STATUS_APPLIED)
    assert total_all == 2
    assert total_applied == 1
    assert applied[0].id == r2.id


async def test_get_application_returns_none_when_wrong_user() -> None:
    user_id = 71009
    other_user = 71010
    await _ensure_user(user_id)
    await _ensure_user(other_user)
    row = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    fetched = await get_application(other_user, row.id)
    assert fetched is None


async def test_stats_compute_rates_correctly() -> None:
    user_id = 71011
    await _ensure_user(user_id)
    await _wipe(user_id)

    # 4 applied: 2 → interview, 1 → rejected before interview, 1 stays applied
    # of the 2 interviews, 1 → offer, 1 → rejected
    a1 = await create_application(user_id, CreateApplicationRequest(company="A", title="T"))
    a2 = await create_application(user_id, CreateApplicationRequest(company="B", title="T"))
    a3 = await create_application(user_id, CreateApplicationRequest(company="C", title="T"))
    a4 = await create_application(user_id, CreateApplicationRequest(company="D", title="T"))
    for a in (a1, a2, a3, a4):
        await update_status(user_id, a.id, StatusUpdateRequest(to_status=STATUS_APPLIED))
    await update_status(user_id, a1.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW_SCHEDULED))
    await update_status(user_id, a2.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW_SCHEDULED))
    await update_status(user_id, a1.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW_COMPLETED))
    await update_status(user_id, a1.id, StatusUpdateRequest(to_status=STATUS_OFFER))
    await update_status(user_id, a2.id, StatusUpdateRequest(to_status=STATUS_REJECTED))
    await update_status(user_id, a3.id, StatusUpdateRequest(to_status=STATUS_REJECTED))

    s = await stats(user_id)
    assert s.total == 4
    assert s.applied == 4  # everyone applied at some point
    assert s.interviews == 2
    assert s.offers == 1
    assert s.rejections == 2
    # interview_rate = 2 interviews / 4 applied = 0.5
    assert s.interview_rate == 0.5
    # offer_rate = 1 offer / 4 applied = 0.25
    assert s.offer_rate == 0.25


async def test_create_tailored_status_keeps_applied_at_null() -> None:
    user_id = 71012
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await create_application(
        user_id,
        CreateApplicationRequest(company="Acme", title="Eng", status=STATUS_TAILORED),
    )
    assert row.applied_at is None
    assert row.status == STATUS_TAILORED


async def test_create_applied_status_sets_applied_at() -> None:
    user_id = 71013
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await create_application(
        user_id,
        CreateApplicationRequest(company="Acme", title="Eng", status=STATUS_APPLIED),
    )
    assert row.applied_at is not None
