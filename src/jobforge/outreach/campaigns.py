"""Outreach campaign service — CRUD + status flow + event log + metrics.

A campaign is a long-lived thread around one (contact, optional
application). Messages are immutable once sent; a fresh message means a
new `recruiter_messages` row plus a `message_events` entry. Status moves
forward via :func:`update_status`; the event log is cumulative so metrics
work even after a campaign closes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.applications import ApplicationError
from jobforge.db.models import (
    MessageEvent,
    OutreachCampaign,
    RecruiterContact,
    RecruiterMessage,
)
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger
from jobforge.outreach.contacts import OutreachError
from jobforge.outreach.messages import (
    ALL_KINDS,
    DraftedMessage,
    MessageContext,
    generate_message,
)
from jobforge.outreach.status import (
    ALL_STATUSES,
    STATUS_CLOSED,
    STATUS_DRAFTED,
    STATUS_IGNORED,
    STATUS_INTERVIEW,
    STATUS_REPLIED,
    STATUS_SENT,
    is_forward_transition,
    is_valid_status,
)

log = get_logger("jobforge.outreach.campaigns")

DEFAULT_FOLLOW_UP_DAYS = 7


@dataclass
class CreateCampaignRequest:
    contact_id: int
    application_id: int | None = None
    interview_plan_id: int | None = None
    goal: str = "initial_outreach"
    notes: str | None = None


@dataclass
class StatusUpdateRequest:
    to_status: str
    notes: str | None = None
    occurred_at: datetime | None = None


@dataclass
class DraftMessageRequest:
    kind: str
    ctx: MessageContext
    channel: str | None = None


@dataclass
class OutreachMetrics:
    total_campaigns: int
    by_status: dict[str, int]
    sent: int
    replied: int
    interviews: int
    response_rate: float
    interview_rate: float
    referral_rate: float


async def _require_contact(
    session: AsyncSession, user_id: int, contact_id: int
) -> RecruiterContact:
    contact = await session.get(RecruiterContact, contact_id)
    if contact is None or contact.user_id != user_id:
        raise OutreachError(f"contact {contact_id} not found")
    return contact


async def create_campaign(
    user_id: int, req: CreateCampaignRequest
) -> OutreachCampaign:
    if req.goal not in ALL_KINDS:
        raise OutreachError(
            f"invalid goal '{req.goal}' (allowed: {list(ALL_KINDS)})"
        )
    async with session_scope() as session:
        await _require_contact(session, user_id, req.contact_id)
        row = OutreachCampaign(
            user_id=user_id,
            contact_id=req.contact_id,
            application_id=req.application_id,
            interview_plan_id=req.interview_plan_id,
            goal=req.goal,
            status=STATUS_DRAFTED,
            notes=req.notes,
        )
        session.add(row)
        await session.flush()
        session.add(
            MessageEvent(
                campaign_id=row.id,
                event_type="created",
                to_status=STATUS_DRAFTED,
                notes=req.notes,
            )
        )
        await session.flush()
        await session.refresh(row)
        session.expunge(row)
        log.info(
            "outreach.campaign.created",
            extra={
                "campaign_id": row.id,
                "contact_id": req.contact_id,
                "goal": req.goal,
            },
        )
        return row


async def list_campaigns(
    user_id: int,
    *,
    status: str | None = None,
    contact_id: int | None = None,
    application_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[OutreachCampaign]]:
    async with session_scope() as session:
        filters = [OutreachCampaign.user_id == user_id]
        if status:
            filters.append(OutreachCampaign.status == status)
        if contact_id is not None:
            filters.append(OutreachCampaign.contact_id == contact_id)
        if application_id is not None:
            filters.append(OutreachCampaign.application_id == application_id)
        total = int(
            (
                await session.execute(
                    select(func.count(OutreachCampaign.id)).where(*filters)
                )
            ).scalar_one()
        )
        rows = (
            await session.execute(
                select(OutreachCampaign)
                .where(*filters)
                .order_by(desc(OutreachCampaign.last_updated_at))
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return total, list(rows)


async def get_campaign(user_id: int, campaign_id: int) -> OutreachCampaign | None:
    async with session_scope() as session:
        row = await session.get(OutreachCampaign, campaign_id)
        if row is None or row.user_id != user_id:
            return None
        session.expunge(row)
        return row


async def list_events(campaign_id: int) -> list[MessageEvent]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(MessageEvent)
                .where(MessageEvent.campaign_id == campaign_id)
                .order_by(MessageEvent.occurred_at.asc(), MessageEvent.id.asc())
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return list(rows)


async def list_messages(campaign_id: int) -> list[RecruiterMessage]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(RecruiterMessage)
                .where(RecruiterMessage.campaign_id == campaign_id)
                .order_by(RecruiterMessage.created_at.asc(), RecruiterMessage.id.asc())
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return list(rows)


async def draft_message(
    user_id: int,
    campaign_id: int,
    req: DraftMessageRequest,
) -> RecruiterMessage:
    """Generate a deterministic draft and store it under the campaign.

    Status stays at `drafted` until :func:`mark_sent` records the send.
    """
    drafted: DraftedMessage = generate_message(req.kind, req.ctx)
    channel = req.channel or drafted.channel
    async with session_scope() as session:
        campaign = await session.get(OutreachCampaign, campaign_id)
        if campaign is None or campaign.user_id != user_id:
            raise OutreachError(f"campaign {campaign_id} not found")
        row = RecruiterMessage(
            campaign_id=campaign_id,
            kind=drafted.kind,
            channel=channel,
            subject=drafted.subject,
            body=drafted.body,
            template_version=drafted.template_version,
            extra_json={"fields_used": dict(drafted.fields_used)},
        )
        session.add(row)
        await session.flush()
        session.add(
            MessageEvent(
                campaign_id=campaign_id,
                message_id=row.id,
                event_type="drafted",
                notes=None,
            )
        )
        await session.flush()
        await session.refresh(row)
        session.expunge(row)
        log.info(
            "outreach.message.drafted",
            extra={
                "campaign_id": campaign_id,
                "message_id": row.id,
                "kind": drafted.kind,
            },
        )
        return row


async def mark_sent(
    user_id: int,
    campaign_id: int,
    message_id: int,
    *,
    occurred_at: datetime | None = None,
    notes: str | None = None,
    follow_up_in_days: int = DEFAULT_FOLLOW_UP_DAYS,
) -> OutreachCampaign:
    """Record that a drafted message went out and advance status."""
    when = occurred_at or datetime.now(UTC)
    async with session_scope() as session:
        campaign = await session.get(OutreachCampaign, campaign_id)
        if campaign is None or campaign.user_id != user_id:
            raise OutreachError(f"campaign {campaign_id} not found")
        message = await session.get(RecruiterMessage, message_id)
        if message is None or message.campaign_id != campaign_id:
            raise OutreachError(
                f"message {message_id} not part of campaign {campaign_id}"
            )
        if message.sent_at is None:
            message.sent_at = when
        from_status = campaign.status
        if campaign.status == STATUS_DRAFTED:
            campaign.status = STATUS_SENT
            event_type = "sent"
        else:
            event_type = "sent_additional"
        campaign.last_event_at = when
        if follow_up_in_days and follow_up_in_days > 0:
            campaign.follow_up_due_at = when + timedelta(days=follow_up_in_days)
        session.add(
            MessageEvent(
                campaign_id=campaign_id,
                message_id=message_id,
                event_type=event_type,
                from_status=from_status,
                to_status=campaign.status,
                notes=notes,
                occurred_at=when,
            )
        )
        await session.flush()
        await session.refresh(campaign)
        session.expunge(campaign)
        log.info(
            "outreach.message.sent",
            extra={
                "campaign_id": campaign_id,
                "message_id": message_id,
                "follow_up_due": campaign.follow_up_due_at.isoformat()
                if campaign.follow_up_due_at
                else None,
            },
        )
        return campaign


async def update_status(
    user_id: int,
    campaign_id: int,
    req: StatusUpdateRequest,
) -> OutreachCampaign:
    if not is_valid_status(req.to_status):
        raise OutreachError(f"invalid status '{req.to_status}' (allowed: {list(ALL_STATUSES)})")
    when = req.occurred_at or datetime.now(UTC)
    async with session_scope() as session:
        campaign = await session.get(OutreachCampaign, campaign_id)
        if campaign is None or campaign.user_id != user_id:
            raise OutreachError(f"campaign {campaign_id} not found")
        from_status = campaign.status
        if from_status == req.to_status:
            session.expunge(campaign)
            return campaign
        event_type = (
            "status_change"
            if is_forward_transition(from_status, req.to_status)
            else "status_change_unusual"
        )
        campaign.status = req.to_status
        campaign.last_event_at = when
        if req.to_status == STATUS_REPLIED:
            # Clear the pending follow-up — we got a response.
            campaign.follow_up_due_at = None
            await _mark_last_replied(session, campaign_id, when)
        elif req.to_status == STATUS_INTERVIEW:
            campaign.follow_up_due_at = None
        session.add(
            MessageEvent(
                campaign_id=campaign_id,
                event_type=event_type,
                from_status=from_status,
                to_status=req.to_status,
                notes=req.notes,
                occurred_at=when,
            )
        )
        await session.flush()
        await session.refresh(campaign)
        session.expunge(campaign)
        log.info(
            "outreach.status_change",
            extra={
                "campaign_id": campaign_id,
                "from": from_status,
                "to": req.to_status,
                "unusual": event_type == "status_change_unusual",
            },
        )
        return campaign


async def _mark_last_replied(
    session: AsyncSession, campaign_id: int, when: datetime
) -> None:
    last = (
        await session.execute(
            select(RecruiterMessage)
            .where(RecruiterMessage.campaign_id == campaign_id)
            .where(RecruiterMessage.sent_at.is_not(None))
            .order_by(desc(RecruiterMessage.sent_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is not None and last.replied_at is None:
        last.replied_at = when


async def list_due_follow_ups(
    user_id: int, *, now: datetime | None = None, limit: int = 50
) -> list[OutreachCampaign]:
    cutoff = now or datetime.now(UTC)
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(OutreachCampaign)
                .where(OutreachCampaign.user_id == user_id)
                .where(OutreachCampaign.status == STATUS_SENT)
                .where(OutreachCampaign.follow_up_due_at.is_not(None))
                .where(OutreachCampaign.follow_up_due_at <= cutoff)
                .order_by(OutreachCampaign.follow_up_due_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return list(rows)


async def list_recent_replies(
    user_id: int, *, limit: int = 50
) -> list[OutreachCampaign]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(OutreachCampaign)
                .where(OutreachCampaign.user_id == user_id)
                .where(OutreachCampaign.status.in_([STATUS_REPLIED, STATUS_INTERVIEW]))
                .order_by(desc(OutreachCampaign.last_event_at))
                .limit(limit)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return list(rows)


async def compute_metrics(user_id: int) -> OutreachMetrics:
    """Funnel metrics — cumulative across the event log.

    `response_rate` = replied / sent.
    `interview_rate` = interviews / sent.
    `referral_rate` = replied + interview campaigns whose goal was
                      `referral_request`, divided by sent referral asks.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(OutreachCampaign.status, func.count(OutreachCampaign.id))
            .where(OutreachCampaign.user_id == user_id)
            .group_by(OutreachCampaign.status)
        )
        by_status: dict[str, int] = {s: int(c) for s, c in result.all()}

        async def _reached(targets: set[str]) -> int:
            stmt = (
                select(func.count(func.distinct(MessageEvent.campaign_id)))
                .select_from(MessageEvent)
                .join(
                    OutreachCampaign,
                    OutreachCampaign.id == MessageEvent.campaign_id,
                )
                .where(OutreachCampaign.user_id == user_id)
                .where(MessageEvent.to_status.in_(targets))
            )
            return int((await session.execute(stmt)).scalar_one() or 0)

        sent = await _reached({STATUS_SENT, STATUS_REPLIED, STATUS_INTERVIEW, STATUS_IGNORED, STATUS_CLOSED})
        replied = await _reached({STATUS_REPLIED, STATUS_INTERVIEW})
        interviews = await _reached({STATUS_INTERVIEW})

        referral_sent_stmt = (
            select(func.count(func.distinct(MessageEvent.campaign_id)))
            .select_from(MessageEvent)
            .join(
                OutreachCampaign,
                OutreachCampaign.id == MessageEvent.campaign_id,
            )
            .where(OutreachCampaign.user_id == user_id)
            .where(OutreachCampaign.goal == "referral_request")
            .where(MessageEvent.to_status.in_([STATUS_SENT, STATUS_REPLIED, STATUS_INTERVIEW, STATUS_IGNORED, STATUS_CLOSED]))
        )
        referral_sent = int(
            (await session.execute(referral_sent_stmt)).scalar_one() or 0
        )
        referral_replied_stmt = (
            select(func.count(func.distinct(MessageEvent.campaign_id)))
            .select_from(MessageEvent)
            .join(
                OutreachCampaign,
                OutreachCampaign.id == MessageEvent.campaign_id,
            )
            .where(OutreachCampaign.user_id == user_id)
            .where(OutreachCampaign.goal == "referral_request")
            .where(MessageEvent.to_status.in_([STATUS_REPLIED, STATUS_INTERVIEW]))
        )
        referral_replied = int(
            (await session.execute(referral_replied_stmt)).scalar_one() or 0
        )

    total = sum(by_status.values())

    def _rate(n: int, d: int) -> float:
        return round(n / d, 4) if d > 0 else 0.0

    return OutreachMetrics(
        total_campaigns=total,
        by_status=by_status,
        sent=sent,
        replied=replied,
        interviews=interviews,
        response_rate=_rate(replied, sent),
        interview_rate=_rate(interviews, sent),
        referral_rate=_rate(referral_replied, referral_sent),
    )


# ---------------- serialization ----------------


def campaign_to_dict(c: OutreachCampaign) -> dict[str, Any]:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "contact_id": c.contact_id,
        "application_id": c.application_id,
        "interview_plan_id": c.interview_plan_id,
        "goal": c.goal,
        "status": c.status,
        "follow_up_due_at": c.follow_up_due_at.isoformat() if c.follow_up_due_at else None,
        "last_event_at": c.last_event_at.isoformat() if c.last_event_at else None,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_updated_at": c.last_updated_at.isoformat() if c.last_updated_at else None,
    }


def message_row_to_dict(m: RecruiterMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "campaign_id": m.campaign_id,
        "kind": m.kind,
        "channel": m.channel,
        "subject": m.subject,
        "body": m.body,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "replied_at": m.replied_at.isoformat() if m.replied_at else None,
        "template_version": m.template_version,
        "polish_model": m.polish_model,
        "extra_json": dict(m.extra_json) if m.extra_json else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def event_to_dict(e: MessageEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "campaign_id": e.campaign_id,
        "message_id": e.message_id,
        "event_type": e.event_type,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "notes": e.notes,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
    }


def metrics_to_dict(m: OutreachMetrics) -> dict[str, Any]:
    return {
        "total_campaigns": m.total_campaigns,
        "by_status": dict(m.by_status),
        "sent": m.sent,
        "replied": m.replied,
        "interviews": m.interviews,
        "response_rate": m.response_rate,
        "interview_rate": m.interview_rate,
        "referral_rate": m.referral_rate,
    }


# Re-exported so the API layer doesn't need to import multiple modules.
__all__ = [
    "CreateCampaignRequest",
    "DraftMessageRequest",
    "OutreachMetrics",
    "StatusUpdateRequest",
    "campaign_to_dict",
    "compute_metrics",
    "create_campaign",
    "draft_message",
    "event_to_dict",
    "get_campaign",
    "list_campaigns",
    "list_due_follow_ups",
    "list_events",
    "list_messages",
    "list_recent_replies",
    "mark_sent",
    "message_row_to_dict",
    "metrics_to_dict",
    "update_status",
]


# Make ApplicationError reachable for callers expecting the same shape as
# the application service. Keep as a module attribute, not a re-export, so
# isort doesn't reorder it.
_ = ApplicationError
