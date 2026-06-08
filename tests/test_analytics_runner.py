"""Scheduler/runner analytics-summary tests (mocked telegram + DB)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from jobforge.db.models import (
    AnalyticsSnapshot,
    Application,
    ApplicationEvent,
    User,
)
from jobforge.db.session import session_scope
from jobforge.scheduler.runner import (
    ANALYTICS_RUN_AT,
    build_default_scheduler,
    deliver_daily_analytics_summary,
    render_analytics_summary_markdown,
)

USER_BASE = 98000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Sched", email=f"s-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        app_ids = [
            a.id
            for a in (
                await session.execute(
                    Application.__table__.select().where(
                        Application.user_id == user_id
                    )
                )
            ).all()
        ]
        if app_ids:
            await session.execute(
                delete(ApplicationEvent).where(
                    ApplicationEvent.application_id.in_(app_ids)
                )
            )
            await session.execute(
                delete(Application).where(Application.id.in_(app_ids))
            )
        await session.execute(
            delete(AnalyticsSnapshot).where(AnalyticsSnapshot.user_id == user_id)
        )


# ---------------- markdown renderer ----------------


def test_render_analytics_summary_markdown_basic_fields() -> None:
    body = render_analytics_summary_markdown(
        funnel_stages_dict={
            "applications_created": 5,
            "applications_submitted": 3,
            "interviews_scheduled": 2,
            "interviews_completed": 1,
            "offers_received": 1,
            "offers_accepted": 0,
        },
        conversions_dict={
            "apply_to_reply": 0.33,
            "apply_to_interview": 0.66,
            "interview_to_offer": 0.5,
        },
        recs=[{"title": "Lean into lever"}, {"title": "Send more follow_up messages"}],
    )
    assert "Applications: 5" in body
    assert "Interviews: 2 scheduled" in body
    assert "Apply → interview: 66%" in body
    assert "Lean into lever" in body


def test_render_analytics_summary_markdown_skips_recs_section_when_empty() -> None:
    body = render_analytics_summary_markdown(
        funnel_stages_dict={
            "applications_created": 0,
            "applications_submitted": 0,
            "interviews_scheduled": 0,
            "interviews_completed": 0,
            "offers_received": 0,
            "offers_accepted": 0,
        },
        conversions_dict={
            "apply_to_reply": 0,
            "apply_to_interview": 0,
            "interview_to_offer": 0,
        },
        recs=[],
    )
    assert "Recommendations" not in body


def test_render_analytics_summary_markdown_caps_at_three_recs() -> None:
    body = render_analytics_summary_markdown(
        funnel_stages_dict={
            "applications_created": 0,
            "applications_submitted": 0,
            "interviews_scheduled": 0,
            "interviews_completed": 0,
            "offers_received": 0,
            "offers_accepted": 0,
        },
        conversions_dict={
            "apply_to_reply": 0,
            "apply_to_interview": 0,
            "interview_to_offer": 0,
        },
        recs=[
            {"title": "a"},
            {"title": "b"},
            {"title": "c"},
            {"title": "d"},
            {"title": "e"},
        ],
    )
    # Only the first three rec titles appear.
    assert "- a" in body
    assert "- b" in body
    assert "- c" in body
    assert "- d" not in body


# ---------------- scheduler wiring ----------------


def test_build_default_scheduler_registers_analytics_summary_job() -> None:
    s = build_default_scheduler()
    names = {j.name for j in s.jobs}
    assert "daily_analytics_summary" in names
    assert "daily_digest" in names


def test_analytics_run_at_is_after_digest_run_at() -> None:
    from jobforge.scheduler.runner import DEFAULT_RUN_AT

    assert (ANALYTICS_RUN_AT.hour, ANALYTICS_RUN_AT.minute) > (
        DEFAULT_RUN_AT.hour,
        DEFAULT_RUN_AT.minute,
    )


# ---------------- deliver_daily_analytics_summary ----------------


async def test_deliver_analytics_summary_returns_true_when_send_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    from jobforge.config import get_settings

    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    with patch(
        "jobforge.scheduler.runner._send_message_raw",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        sent = await deliver_daily_analytics_summary()
    assert sent is True
    mock_send.assert_called_once()


async def test_deliver_analytics_summary_writes_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    from jobforge.config import get_settings

    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    with patch(
        "jobforge.scheduler.runner._send_message_raw",
        new=AsyncMock(return_value=True),
    ):
        await deliver_daily_analytics_summary()
    from jobforge.analytics import list_snapshots

    snaps = await list_snapshots(user_id)
    assert len(snaps) == 1


async def test_deliver_analytics_summary_returns_false_on_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    from jobforge.config import get_settings

    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    with patch(
        "jobforge.scheduler.runner._send_message_raw",
        new=AsyncMock(return_value=False),
    ):
        sent = await deliver_daily_analytics_summary()
    assert sent is False
