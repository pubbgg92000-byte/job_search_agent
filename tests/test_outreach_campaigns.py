"""Campaign service tests — CRUD, status flow, metrics, follow-ups, drafts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from jobforge.db.models import (
    Application,
    MessageEvent,
    OutreachCampaign,
    RecruiterContact,
    RecruiterMessage,
    User,
)
from jobforge.db.session import session_scope
from jobforge.outreach import (
    CreateCampaignRequest,
    DraftMessageRequest,
    MessageContext,
    OutreachError,
    StatusUpdateRequest,
    UpsertContactRequest,
    campaign_to_dict,
    compute_metrics,
    create_campaign,
    draft_message,
    event_to_dict,
    get_campaign,
    list_campaigns,
    list_due_follow_ups,
    list_events,
    list_messages,
    list_recent_replies,
    mark_sent,
    message_row_to_dict,
    metrics_to_dict,
    update_status,
    upsert_contact,
)
from jobforge.outreach.status import (
    STATUS_CLOSED,
    STATUS_DRAFTED,
    STATUS_INTERVIEW,
    STATUS_REPLIED,
    STATUS_SENT,
)

USER_BASE = 91000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Camp", email=f"c-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        contact_ids = [
            c.id
            for c in (
                await session.execute(
                    RecruiterContact.__table__.select().where(
                        RecruiterContact.user_id == user_id
                    )
                )
            ).all()
        ]
        campaign_ids = [
            c.id
            for c in (
                await session.execute(
                    OutreachCampaign.__table__.select().where(
                        OutreachCampaign.user_id == user_id
                    )
                )
            ).all()
        ]
        if campaign_ids:
            await session.execute(
                delete(MessageEvent).where(MessageEvent.campaign_id.in_(campaign_ids))
            )
            await session.execute(
                delete(RecruiterMessage).where(
                    RecruiterMessage.campaign_id.in_(campaign_ids)
                )
            )
            await session.execute(
                delete(OutreachCampaign).where(OutreachCampaign.id.in_(campaign_ids))
            )
        if contact_ids:
            await session.execute(
                delete(RecruiterContact).where(RecruiterContact.id.in_(contact_ids))
            )
        await session.execute(delete(Application).where(Application.user_id == user_id))


async def _seed_contact(user_id: int, company: str = "Acme", name: str = "Sam") -> int:
    row = await upsert_contact(
        user_id, UpsertContactRequest(company=company, name=name)
    )
    return row.id


def _ctx() -> MessageContext:
    return MessageContext(
        company="Acme",
        contact_name="Sam",
        role_title="Engineer",
        candidate_name="R",
        matched_skills=["Python"],
        top_skills=["Python"],
    )


# ---------------- create_campaign ----------------


async def test_create_campaign_starts_drafted_and_logs_event() -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    assert camp.status == STATUS_DRAFTED
    events = await list_events(camp.id)
    assert len(events) == 1
    assert events[0].event_type == "created"


async def test_create_campaign_rejects_unknown_contact() -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    with pytest.raises(OutreachError):
        await create_campaign(user_id, CreateCampaignRequest(contact_id=999_999))


async def test_create_campaign_rejects_invalid_goal() -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    with pytest.raises(OutreachError):
        await create_campaign(
            user_id, CreateCampaignRequest(contact_id=cid, goal="conspiracy_dispatch")
        )


# ---------------- listing ----------------


async def test_list_campaigns_filters_by_status() -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    a = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    b = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(user_id, b.id, StatusUpdateRequest(to_status=STATUS_SENT))
    total, rows = await list_campaigns(user_id, status=STATUS_DRAFTED)
    assert total == 1
    assert rows[0].id == a.id


async def test_get_campaign_returns_none_for_unowned() -> None:
    user_id = USER_BASE + 5
    user_other = USER_BASE + 6
    await _ensure_user(user_id)
    await _ensure_user(user_other)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    assert await get_campaign(user_other, camp.id) is None


# ---------------- draft + sent ----------------


async def test_draft_message_persists_and_logs_event() -> None:
    user_id = USER_BASE + 7
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id,
        camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    assert msg.id is not None
    msgs = await list_messages(camp.id)
    assert len(msgs) == 1
    events = await list_events(camp.id)
    assert any(e.event_type == "drafted" for e in events)


async def test_draft_message_unknown_campaign_raises() -> None:
    user_id = USER_BASE + 8
    await _ensure_user(user_id)
    with pytest.raises(OutreachError):
        await draft_message(
            user_id,
            999_999,
            DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
        )


async def test_mark_sent_advances_status_and_schedules_follow_up() -> None:
    user_id = USER_BASE + 9
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id,
        camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    now = datetime.now(UTC)
    advanced = await mark_sent(
        user_id, camp.id, msg.id, occurred_at=now, follow_up_in_days=5
    )
    assert advanced.status == STATUS_SENT
    assert advanced.follow_up_due_at is not None
    delta = advanced.follow_up_due_at - now
    assert 4 <= delta.days <= 5


async def test_mark_sent_zero_follow_up_keeps_due_at_none() -> None:
    user_id = USER_BASE + 10
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    advanced = await mark_sent(user_id, camp.id, msg.id, follow_up_in_days=0)
    assert advanced.follow_up_due_at is None


async def test_mark_sent_unknown_message_raises() -> None:
    user_id = USER_BASE + 11
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    with pytest.raises(OutreachError):
        await mark_sent(user_id, camp.id, 999_999)


# ---------------- status flow ----------------


async def test_update_status_forward_logs_status_change() -> None:
    user_id = USER_BASE + 12
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    updated = await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_SENT)
    )
    assert updated.status == STATUS_SENT
    events = await list_events(camp.id)
    assert any(e.event_type == "status_change" for e in events)


async def test_update_status_backwards_logs_unusual_event() -> None:
    user_id = USER_BASE + 13
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW)
    )
    await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_DRAFTED)
    )
    events = await list_events(camp.id)
    assert any(e.event_type == "status_change_unusual" for e in events)


async def test_update_status_replied_clears_follow_up_and_stamps_message() -> None:
    user_id = USER_BASE + 14
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    await mark_sent(user_id, camp.id, msg.id, follow_up_in_days=7)
    updated = await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_REPLIED)
    )
    assert updated.status == STATUS_REPLIED
    assert updated.follow_up_due_at is None
    msgs = await list_messages(camp.id)
    assert msgs[-1].replied_at is not None


async def test_update_status_unknown_campaign_raises() -> None:
    user_id = USER_BASE + 15
    await _ensure_user(user_id)
    with pytest.raises(OutreachError):
        await update_status(
            user_id, 999_999, StatusUpdateRequest(to_status=STATUS_SENT)
        )


async def test_update_status_rejects_invalid_status() -> None:
    user_id = USER_BASE + 16
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    with pytest.raises(OutreachError):
        await update_status(
            user_id, camp.id, StatusUpdateRequest(to_status="not-a-status")
        )


async def test_update_status_same_status_is_noop() -> None:
    user_id = USER_BASE + 17
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    updated = await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_DRAFTED)
    )
    assert updated.status == STATUS_DRAFTED
    events = await list_events(camp.id)
    # Only the original `created` event.
    assert len(events) == 1


# ---------------- follow-up queries ----------------


async def test_list_due_follow_ups_filters_by_cutoff() -> None:
    user_id = USER_BASE + 18
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    past = datetime.now(UTC) - timedelta(days=10)
    await mark_sent(user_id, camp.id, msg.id, occurred_at=past, follow_up_in_days=3)
    due = await list_due_follow_ups(user_id, now=datetime.now(UTC))
    assert any(c.id == camp.id for c in due)


async def test_list_due_follow_ups_skips_future_due() -> None:
    user_id = USER_BASE + 19
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    await mark_sent(user_id, camp.id, msg.id, follow_up_in_days=30)
    due = await list_due_follow_ups(user_id, now=datetime.now(UTC))
    assert all(c.id != camp.id for c in due)


async def test_list_recent_replies_returns_replied_and_interview() -> None:
    user_id = USER_BASE + 20
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp_a = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(
        user_id, camp_a.id, StatusUpdateRequest(to_status=STATUS_SENT)
    )
    await update_status(
        user_id, camp_a.id, StatusUpdateRequest(to_status=STATUS_REPLIED)
    )
    camp_b = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(
        user_id, camp_b.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW)
    )
    replies = await list_recent_replies(user_id)
    ids = {c.id for c in replies}
    assert camp_a.id in ids
    assert camp_b.id in ids


# ---------------- metrics ----------------


async def test_compute_metrics_zero_when_no_data() -> None:
    user_id = USER_BASE + 21
    await _ensure_user(user_id)
    await _wipe(user_id)
    m = await compute_metrics(user_id)
    assert m.total_campaigns == 0
    assert m.response_rate == 0.0
    assert m.interview_rate == 0.0
    assert m.referral_rate == 0.0


async def test_compute_metrics_response_rate() -> None:
    user_id = USER_BASE + 22
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    # Two campaigns sent, one replied.
    a = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    b = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    for c in (a, b):
        await update_status(user_id, c.id, StatusUpdateRequest(to_status=STATUS_SENT))
    await update_status(user_id, a.id, StatusUpdateRequest(to_status=STATUS_REPLIED))
    m = await compute_metrics(user_id)
    assert m.sent == 2
    assert m.replied == 1
    assert m.response_rate == 0.5


async def test_compute_metrics_interview_rate() -> None:
    user_id = USER_BASE + 23
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    a = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    b = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    for c in (a, b):
        await update_status(user_id, c.id, StatusUpdateRequest(to_status=STATUS_SENT))
    await update_status(user_id, a.id, StatusUpdateRequest(to_status=STATUS_INTERVIEW))
    m = await compute_metrics(user_id)
    assert m.interviews == 1
    assert m.interview_rate == 0.5


async def test_compute_metrics_referral_rate_scoped_to_referral_goal() -> None:
    user_id = USER_BASE + 24
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    a = await create_campaign(
        user_id,
        CreateCampaignRequest(contact_id=cid, goal="referral_request"),
    )
    b = await create_campaign(
        user_id,
        CreateCampaignRequest(contact_id=cid, goal="initial_outreach"),
    )
    for c in (a, b):
        await update_status(user_id, c.id, StatusUpdateRequest(to_status=STATUS_SENT))
    await update_status(user_id, a.id, StatusUpdateRequest(to_status=STATUS_REPLIED))
    m = await compute_metrics(user_id)
    # 1 referral sent → 1 replied. The initial-outreach reply doesn't count.
    assert m.referral_rate == 1.0


async def test_compute_metrics_cumulative_across_status_history() -> None:
    """A campaign that hit sent → replied → closed still contributes."""
    user_id = USER_BASE + 25
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    for st in (STATUS_SENT, STATUS_REPLIED, STATUS_INTERVIEW, STATUS_CLOSED):
        await update_status(user_id, camp.id, StatusUpdateRequest(to_status=st))
    m = await compute_metrics(user_id)
    assert m.sent == 1
    assert m.replied == 1
    assert m.interviews == 1


async def test_metrics_to_dict_keys() -> None:
    user_id = USER_BASE + 26
    await _ensure_user(user_id)
    await _wipe(user_id)
    m = await compute_metrics(user_id)
    d = metrics_to_dict(m)
    expected = {
        "total_campaigns",
        "by_status",
        "sent",
        "replied",
        "interviews",
        "response_rate",
        "interview_rate",
        "referral_rate",
    }
    assert set(d.keys()) == expected


# ---------------- serialization ----------------


async def test_campaign_to_dict_keys() -> None:
    user_id = USER_BASE + 27
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    d = campaign_to_dict(camp)
    expected = {
        "id", "user_id", "contact_id", "application_id", "interview_plan_id",
        "goal", "status", "follow_up_due_at", "last_event_at", "notes",
        "created_at", "last_updated_at",
    }
    assert expected <= set(d.keys())


async def test_message_row_to_dict_keys() -> None:
    user_id = USER_BASE + 28
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    d = message_row_to_dict(msg)
    expected = {
        "id", "campaign_id", "kind", "channel", "subject", "body",
        "sent_at", "replied_at", "template_version", "polish_model",
        "extra_json", "created_at",
    }
    assert set(d.keys()) == expected


async def test_event_to_dict_keys() -> None:
    user_id = USER_BASE + 29
    await _ensure_user(user_id)
    await _wipe(user_id)
    cid = await _seed_contact(user_id)
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    events = await list_events(camp.id)
    d = event_to_dict(events[0])
    expected = {
        "id", "campaign_id", "message_id", "event_type",
        "from_status", "to_status", "notes", "occurred_at",
    }
    assert set(d.keys()) == expected
