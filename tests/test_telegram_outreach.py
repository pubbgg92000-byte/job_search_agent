"""Tests for the Phase 3D telegram commands (/outreach, /replies, /followups)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from jobforge.config import get_settings
from jobforge.db.models import (
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
    StatusUpdateRequest,
    UpsertContactRequest,
    create_campaign,
    draft_message,
    mark_sent,
    update_status,
    upsert_contact,
)
from jobforge.outreach.status import STATUS_REPLIED, STATUS_SENT
from jobforge.telegram.bot import build_default_bot

USER_BASE = 93000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="TG", email=f"tg-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        camp_ids = [
            c.id
            for c in (
                await session.execute(
                    OutreachCampaign.__table__.select().where(
                        OutreachCampaign.user_id == user_id
                    )
                )
            ).all()
        ]
        if camp_ids:
            await session.execute(
                delete(MessageEvent).where(MessageEvent.campaign_id.in_(camp_ids))
            )
            await session.execute(
                delete(RecruiterMessage).where(
                    RecruiterMessage.campaign_id.in_(camp_ids)
                )
            )
            await session.execute(
                delete(OutreachCampaign).where(OutreachCampaign.id.in_(camp_ids))
            )
        await session.execute(
            delete(RecruiterContact).where(RecruiterContact.user_id == user_id)
        )


def _ctx() -> MessageContext:
    return MessageContext(
        company="Acme", contact_name="Sam", role_title="Engineer", matched_skills=["Python"]
    )


async def test_outreach_command_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    bot = build_default_bot()
    reply = await bot.dispatch("/outreach")
    assert reply is not None
    assert "No outreach campaigns" in reply


async def test_outreach_command_summarises_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    cid = (await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )).id
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_SENT)
    )
    bot = build_default_bot()
    reply = await bot.dispatch("/outreach 5")
    assert reply is not None
    assert "sent" in reply
    assert "Recent" in reply


async def test_replies_command_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    bot = build_default_bot()
    reply = await bot.dispatch("/replies")
    assert reply == "No replies yet."


async def test_replies_command_lists_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    cid = (await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )).id
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_SENT)
    )
    await update_status(
        user_id, camp.id, StatusUpdateRequest(to_status=STATUS_REPLIED)
    )
    bot = build_default_bot()
    reply = await bot.dispatch("/replies 5")
    assert reply is not None
    assert f"#{camp.id}" in reply


async def test_followups_command_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = USER_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    bot = build_default_bot()
    reply = await bot.dispatch("/followups")
    assert reply is not None
    assert "No follow-ups due" in reply


async def test_followups_command_shows_due_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = USER_BASE + 6
    await _ensure_user(user_id)
    await _wipe(user_id)
    monkeypatch.setattr(get_settings(), "sole_user_id", user_id, raising=False)
    cid = (await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )).id
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=cid))
    msg = await draft_message(
        user_id,
        camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    past = datetime.now(UTC) - timedelta(days=10)
    await mark_sent(user_id, camp.id, msg.id, occurred_at=past, follow_up_in_days=3)
    bot = build_default_bot()
    reply = await bot.dispatch("/followups")
    assert reply is not None
    assert f"#{camp.id}" in reply


async def test_help_command_lists_new_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = build_default_bot()
    reply = await bot.dispatch("/help")
    assert reply is not None
    assert "/outreach" in reply
    assert "/replies" in reply
    assert "/followups" in reply


async def test_default_bot_registers_new_handlers() -> None:
    bot = build_default_bot()
    assert "outreach" in bot.handlers
    assert "replies" in bot.handlers
    assert "followups" in bot.handlers
