"""Outreach performance analytics.

Three views:

- by_message_kind: for each of the 5 message kinds (initial, referral,
  HM intro, follow-up, thank-you), the count sent / replied / interview
  and the response rate.
- by_company: per-company campaign volume + reply rate.
- follow_up_effectiveness: did campaigns where a follow-up was sent
  achieve a higher reply rate than those that didn't?

Cumulative across the event log — same posture as
:func:`jobforge.outreach.campaigns.compute_metrics`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.db.models import (
    MessageEvent,
    OutreachCampaign,
    RecruiterContact,
    RecruiterMessage,
)
from jobforge.db.session import session_scope
from jobforge.outreach.messages import ALL_KINDS
from jobforge.outreach.status import (
    STATUS_INTERVIEW,
    STATUS_REPLIED,
    STATUS_SENT,
)


@dataclass(frozen=True)
class OutreachKindRow:
    kind: str
    sent: int
    replied: int
    interviews: int

    @property
    def response_rate(self) -> float:
        return round(self.replied / self.sent, 4) if self.sent else 0.0


@dataclass(frozen=True)
class OutreachCompanyRow:
    company: str
    campaigns: int
    sent: int
    replied: int
    interviews: int

    @property
    def response_rate(self) -> float:
        return round(self.replied / self.sent, 4) if self.sent else 0.0


@dataclass(frozen=True)
class FollowUpEffectiveness:
    campaigns_with_follow_up: int
    campaigns_without_follow_up: int
    reply_rate_with_follow_up: float
    reply_rate_without_follow_up: float

    @property
    def follow_up_lift(self) -> float:
        return round(
            self.reply_rate_with_follow_up - self.reply_rate_without_follow_up, 4
        )


@dataclass(frozen=True)
class OutreachReport:
    by_kind: list[OutreachKindRow]
    by_company: list[OutreachCompanyRow]
    follow_up: FollowUpEffectiveness


_SENT_STATUSES = {STATUS_SENT, STATUS_REPLIED, STATUS_INTERVIEW, "ignored", "closed"}
_REPLIED_STATUSES = {STATUS_REPLIED, STATUS_INTERVIEW}
_INTERVIEW_STATUSES = {STATUS_INTERVIEW}


async def _campaign_ids_for_status(
    session: AsyncSession, user_id: int, statuses: set[str]
) -> set[int]:
    stmt = (
        select(distinct(MessageEvent.campaign_id))
        .select_from(MessageEvent)
        .join(OutreachCampaign, OutreachCampaign.id == MessageEvent.campaign_id)
        .where(OutreachCampaign.user_id == user_id)
        .where(MessageEvent.to_status.in_(statuses))
    )
    return {int(c) for (c,) in (await session.execute(stmt)).all()}


async def _kinds_for_campaign_ids(
    session: AsyncSession, ids: set[int]
) -> dict[int, set[str]]:
    """Return the set of message-kinds dispatched per campaign id."""
    if not ids:
        return {}
    stmt = select(
        RecruiterMessage.campaign_id, RecruiterMessage.kind
    ).where(RecruiterMessage.campaign_id.in_(ids))
    out: dict[int, set[str]] = {}
    for cid, kind in (await session.execute(stmt)).all():
        out.setdefault(int(cid), set()).add(str(kind))
    return out


async def _follow_up_campaign_ids(
    session: AsyncSession, user_id: int
) -> set[int]:
    """Campaigns that ever drafted/sent a `follow_up` message kind."""
    stmt = (
        select(distinct(RecruiterMessage.campaign_id))
        .select_from(RecruiterMessage)
        .join(OutreachCampaign, OutreachCampaign.id == RecruiterMessage.campaign_id)
        .where(OutreachCampaign.user_id == user_id)
        .where(RecruiterMessage.kind == "follow_up")
    )
    return {int(c) for (c,) in (await session.execute(stmt)).all()}


async def _company_for_campaign_ids(
    session: AsyncSession, ids: set[int]
) -> dict[int, str]:
    if not ids:
        return {}
    stmt = (
        select(OutreachCampaign.id, RecruiterContact.company)
        .select_from(OutreachCampaign)
        .join(RecruiterContact, RecruiterContact.id == OutreachCampaign.contact_id)
        .where(OutreachCampaign.id.in_(ids))
    )
    return {int(cid): str(company) for cid, company in (await session.execute(stmt)).all()}


async def compute_outreach_report(user_id: int) -> OutreachReport:
    async with session_scope() as session:
        sent_ids = await _campaign_ids_for_status(session, user_id, _SENT_STATUSES)
        replied_ids = await _campaign_ids_for_status(session, user_id, _REPLIED_STATUSES)
        interview_ids = await _campaign_ids_for_status(
            session, user_id, _INTERVIEW_STATUSES
        )
        all_ids = sent_ids | replied_ids | interview_ids
        kinds_per_campaign = await _kinds_for_campaign_ids(session, all_ids)
        companies_per_campaign = await _company_for_campaign_ids(session, all_ids)
        follow_up_ids = await _follow_up_campaign_ids(session, user_id)

    # --- by kind ---
    by_kind: list[OutreachKindRow] = []
    for kind in ALL_KINDS:
        # A campaign counts toward a kind if it ever drafted a message of
        # that kind. One campaign with both initial + follow_up contributes
        # to both rows.
        ids_for_kind = {
            cid for cid, kinds in kinds_per_campaign.items() if kind in kinds
        }
        by_kind.append(
            OutreachKindRow(
                kind=kind,
                sent=len(ids_for_kind & sent_ids),
                replied=len(ids_for_kind & replied_ids),
                interviews=len(ids_for_kind & interview_ids),
            )
        )

    # --- by company ---
    companies: dict[str, dict[str, int]] = {}
    for cid, company in companies_per_campaign.items():
        bucket = companies.setdefault(
            company, {"campaigns": 0, "sent": 0, "replied": 0, "interviews": 0}
        )
        bucket["campaigns"] += 1
        if cid in sent_ids:
            bucket["sent"] += 1
        if cid in replied_ids:
            bucket["replied"] += 1
        if cid in interview_ids:
            bucket["interviews"] += 1
    by_company = sorted(
        (
            OutreachCompanyRow(
                company=name,
                campaigns=b["campaigns"],
                sent=b["sent"],
                replied=b["replied"],
                interviews=b["interviews"],
            )
            for name, b in companies.items()
        ),
        key=lambda r: (-r.replied, -r.interviews, r.company),
    )

    # --- follow-up effectiveness ---
    with_follow = follow_up_ids & sent_ids
    without_follow = sent_ids - follow_up_ids
    with_reply_rate = (
        round(len(with_follow & replied_ids) / len(with_follow), 4)
        if with_follow
        else 0.0
    )
    without_reply_rate = (
        round(len(without_follow & replied_ids) / len(without_follow), 4)
        if without_follow
        else 0.0
    )
    follow_up = FollowUpEffectiveness(
        campaigns_with_follow_up=len(with_follow),
        campaigns_without_follow_up=len(without_follow),
        reply_rate_with_follow_up=with_reply_rate,
        reply_rate_without_follow_up=without_reply_rate,
    )

    return OutreachReport(by_kind=by_kind, by_company=by_company, follow_up=follow_up)


def kind_row_to_dict(r: OutreachKindRow) -> dict[str, Any]:
    return {
        "kind": r.kind,
        "sent": r.sent,
        "replied": r.replied,
        "interviews": r.interviews,
        "response_rate": r.response_rate,
    }


def company_row_to_dict(r: OutreachCompanyRow) -> dict[str, Any]:
    return {
        "company": r.company,
        "campaigns": r.campaigns,
        "sent": r.sent,
        "replied": r.replied,
        "interviews": r.interviews,
        "response_rate": r.response_rate,
    }


def follow_up_to_dict(f: FollowUpEffectiveness) -> dict[str, Any]:
    return {
        "campaigns_with_follow_up": f.campaigns_with_follow_up,
        "campaigns_without_follow_up": f.campaigns_without_follow_up,
        "reply_rate_with_follow_up": f.reply_rate_with_follow_up,
        "reply_rate_without_follow_up": f.reply_rate_without_follow_up,
        "follow_up_lift": f.follow_up_lift,
    }


def outreach_report_to_dict(r: OutreachReport) -> dict[str, Any]:
    return {
        "by_kind": [kind_row_to_dict(x) for x in r.by_kind],
        "by_company": [company_row_to_dict(x) for x in r.by_company],
        "follow_up": follow_up_to_dict(r.follow_up),
    }
