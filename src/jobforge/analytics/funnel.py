"""Funnel analytics — 10-stage end-to-end view across the whole pipeline.

Stages (from PRD):

  jobs_discovered, jobs_saved, applications_created,
  applications_submitted, messages_sent, recruiter_replies,
  interviews_scheduled, interviews_completed, offers_received,
  offers_accepted

Five conversion ratios:

  discovery_to_apply, apply_to_reply, apply_to_interview,
  interview_to_offer, offer_to_acceptance

All cumulative — same posture as :func:`jobforge.applications.stats`. A
campaign or application that has since moved on still contributes to each
prior stage it touched.

This module is pure SQL — no LLM, no network. Other analytics modules
(`sources`, `resumes`, `outreach_perf`, `snapshots`) share the helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.applications.status import (
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_DECLINED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_SAVED,
)
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    DiscoveredJob,
    MessageEvent,
    OutreachCampaign,
)
from jobforge.db.session import session_scope
from jobforge.outreach.status import (
    STATUS_INTERVIEW as OUTREACH_STATUS_INTERVIEW,
)
from jobforge.outreach.status import (
    STATUS_REPLIED as OUTREACH_STATUS_REPLIED,
)
from jobforge.outreach.status import (
    STATUS_SENT as OUTREACH_STATUS_SENT,
)


@dataclass(frozen=True)
class FunnelStages:
    jobs_discovered: int
    jobs_saved: int
    applications_created: int
    applications_submitted: int
    messages_sent: int
    recruiter_replies: int
    interviews_scheduled: int
    interviews_completed: int
    offers_received: int
    offers_accepted: int
    rejections: int


@dataclass(frozen=True)
class ConversionRates:
    discovery_to_apply: float
    apply_to_reply: float
    apply_to_interview: float
    interview_to_offer: float
    offer_to_acceptance: float


@dataclass(frozen=True)
class FunnelReport:
    stages: FunnelStages
    conversions: ConversionRates


# ---------------- helpers ----------------


def _rate(numer: int, denom: int) -> float:
    return round(numer / denom, 4) if denom > 0 else 0.0


async def _count_jobs_discovered(session: AsyncSession) -> int:
    """Total discovered jobs across all sources. Not user-scoped — discovery
    is a shared catalogue in this single-user product."""
    return int(
        (await session.execute(select(func.count(DiscoveredJob.id)))).scalar_one() or 0
    )


async def _count_applications_by_event(
    session: AsyncSession, user_id: int, statuses: set[str]
) -> int:
    """Distinct applications that ever recorded a transition into `statuses`."""
    stmt = (
        select(func.count(func.distinct(ApplicationEvent.application_id)))
        .select_from(ApplicationEvent)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(Application.user_id == user_id)
        .where(ApplicationEvent.to_status.in_(statuses))
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _count_applications_in_status(
    session: AsyncSession, user_id: int, status: str
) -> int:
    """Current count for a status — used for jobs_saved and rejections."""
    stmt = (
        select(func.count(Application.id))
        .where(Application.user_id == user_id)
        .where(Application.status == status)
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _count_outreach_by_event(
    session: AsyncSession, user_id: int, statuses: set[str]
) -> int:
    stmt = (
        select(func.count(func.distinct(MessageEvent.campaign_id)))
        .select_from(MessageEvent)
        .join(OutreachCampaign, OutreachCampaign.id == MessageEvent.campaign_id)
        .where(OutreachCampaign.user_id == user_id)
        .where(MessageEvent.to_status.in_(statuses))
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


# ---------------- public ----------------


# Stage definitions matched to the `applications.status` enum / event log.
_APPLIED_STATUSES: set[str] = {
    STATUS_APPLIED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_INTERVIEW_SCHEDULED_STATUSES: set[str] = {
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_INTERVIEW_COMPLETED_STATUSES: set[str] = {
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_OFFER_STATUSES: set[str] = {STATUS_OFFER, STATUS_ACCEPTED, STATUS_DECLINED}
_ACCEPTED_STATUSES: set[str] = {STATUS_ACCEPTED}


async def compute_stages(user_id: int) -> FunnelStages:
    async with session_scope() as session:
        jobs_discovered = await _count_jobs_discovered(session)
        jobs_saved = await _count_applications_in_status(
            session, user_id, STATUS_SAVED
        )
        applications_created = int(
            (
                await session.execute(
                    select(func.count(Application.id)).where(
                        Application.user_id == user_id
                    )
                )
            ).scalar_one()
            or 0
        )
        applications_submitted = await _count_applications_by_event(
            session, user_id, _APPLIED_STATUSES
        )
        messages_sent = await _count_outreach_by_event(
            session,
            user_id,
            {
                OUTREACH_STATUS_SENT,
                OUTREACH_STATUS_REPLIED,
                OUTREACH_STATUS_INTERVIEW,
                "ignored",
                "closed",
            },
        )
        recruiter_replies = await _count_outreach_by_event(
            session,
            user_id,
            {OUTREACH_STATUS_REPLIED, OUTREACH_STATUS_INTERVIEW},
        )
        interviews_scheduled = await _count_applications_by_event(
            session, user_id, _INTERVIEW_SCHEDULED_STATUSES
        )
        interviews_completed = await _count_applications_by_event(
            session, user_id, _INTERVIEW_COMPLETED_STATUSES
        )
        offers_received = await _count_applications_by_event(
            session, user_id, _OFFER_STATUSES
        )
        offers_accepted = await _count_applications_by_event(
            session, user_id, _ACCEPTED_STATUSES
        )
        rejections = await _count_applications_in_status(
            session, user_id, STATUS_REJECTED
        )
    return FunnelStages(
        jobs_discovered=jobs_discovered,
        jobs_saved=jobs_saved,
        applications_created=applications_created,
        applications_submitted=applications_submitted,
        messages_sent=messages_sent,
        recruiter_replies=recruiter_replies,
        interviews_scheduled=interviews_scheduled,
        interviews_completed=interviews_completed,
        offers_received=offers_received,
        offers_accepted=offers_accepted,
        rejections=rejections,
    )


def compute_conversions(stages: FunnelStages) -> ConversionRates:
    return ConversionRates(
        discovery_to_apply=_rate(stages.applications_submitted, stages.jobs_discovered),
        apply_to_reply=_rate(stages.recruiter_replies, stages.applications_submitted),
        apply_to_interview=_rate(
            stages.interviews_scheduled, stages.applications_submitted
        ),
        interview_to_offer=_rate(stages.offers_received, stages.interviews_completed),
        offer_to_acceptance=_rate(stages.offers_accepted, stages.offers_received),
    )


async def compute_funnel(user_id: int) -> FunnelReport:
    stages = await compute_stages(user_id)
    return FunnelReport(stages=stages, conversions=compute_conversions(stages))


# ---------------- serialization ----------------


def stages_to_dict(s: FunnelStages) -> dict[str, Any]:
    return {
        "jobs_discovered": s.jobs_discovered,
        "jobs_saved": s.jobs_saved,
        "applications_created": s.applications_created,
        "applications_submitted": s.applications_submitted,
        "messages_sent": s.messages_sent,
        "recruiter_replies": s.recruiter_replies,
        "interviews_scheduled": s.interviews_scheduled,
        "interviews_completed": s.interviews_completed,
        "offers_received": s.offers_received,
        "offers_accepted": s.offers_accepted,
        "rejections": s.rejections,
    }


def conversions_to_dict(c: ConversionRates) -> dict[str, Any]:
    return {
        "discovery_to_apply": c.discovery_to_apply,
        "apply_to_reply": c.apply_to_reply,
        "apply_to_interview": c.apply_to_interview,
        "interview_to_offer": c.interview_to_offer,
        "offer_to_acceptance": c.offer_to_acceptance,
    }


def funnel_to_dict(r: FunnelReport) -> dict[str, Any]:
    return {
        "stages": stages_to_dict(r.stages),
        "conversions": conversions_to_dict(r.conversions),
    }
