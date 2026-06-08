"""Funnel + conversion analytics tests."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete

from jobforge.analytics import (
    ConversionRates,
    FunnelStages,
    compute_conversions,
    compute_funnel,
    compute_stages,
    conversions_to_dict,
    funnel_to_dict,
    stages_to_dict,
)
from jobforge.applications import (
    CreateApplicationRequest,
    StatusUpdateRequest,
    create_application,
    update_status,
)
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    DiscoveredJob,
    MessageEvent,
    OutreachCampaign,
    RecruiterContact,
    User,
)
from jobforge.db.session import session_scope
from jobforge.outreach import (
    CreateCampaignRequest,
    UpsertContactRequest,
    create_campaign,
    upsert_contact,
)
from jobforge.outreach import update_status as update_outreach_status
from jobforge.outreach.status import (
    STATUS_INTERVIEW as O_INTERVIEW,
)
from jobforge.outreach.status import (
    STATUS_REPLIED as O_REPLIED,
)
from jobforge.outreach.status import (
    STATUS_SENT as O_SENT,
)

USER_BASE = 94000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Funnel", email=f"f-{user_id}@x.test"))


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
                delete(OutreachCampaign).where(OutreachCampaign.id.in_(camp_ids))
            )
        await session.execute(
            delete(RecruiterContact).where(RecruiterContact.user_id == user_id)
        )
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


# ---------------- compute_conversions (pure) ----------------


def test_conversions_zero_for_empty_stages() -> None:
    c = compute_conversions(
        FunnelStages(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    )
    assert c.discovery_to_apply == 0.0
    assert c.apply_to_reply == 0.0
    assert c.apply_to_interview == 0.0
    assert c.interview_to_offer == 0.0
    assert c.offer_to_acceptance == 0.0


def test_conversions_compute_each_rate_independently() -> None:
    c = compute_conversions(
        FunnelStages(
            jobs_discovered=100,
            jobs_saved=10,
            applications_created=20,
            applications_submitted=10,
            messages_sent=10,
            recruiter_replies=4,
            interviews_scheduled=5,
            interviews_completed=4,
            offers_received=2,
            offers_accepted=1,
            rejections=3,
        )
    )
    assert c.discovery_to_apply == 0.1
    assert c.apply_to_reply == 0.4
    assert c.apply_to_interview == 0.5
    assert c.interview_to_offer == 0.5
    assert c.offer_to_acceptance == 0.5


def test_conversions_rate_uses_apply_denominator_for_reply() -> None:
    c = compute_conversions(
        FunnelStages(
            jobs_discovered=0,
            jobs_saved=0,
            applications_created=0,
            applications_submitted=10,
            messages_sent=10,
            recruiter_replies=3,
            interviews_scheduled=0,
            interviews_completed=0,
            offers_received=0,
            offers_accepted=0,
            rejections=0,
        )
    )
    # reply rate uses applications_submitted, NOT messages_sent
    assert c.apply_to_reply == 0.3


def test_conversions_interview_to_offer_uses_completed_denominator() -> None:
    c = compute_conversions(
        FunnelStages(
            jobs_discovered=0,
            jobs_saved=0,
            applications_created=0,
            applications_submitted=0,
            messages_sent=0,
            recruiter_replies=0,
            interviews_scheduled=10,
            interviews_completed=4,
            offers_received=2,
            offers_accepted=1,
            rejections=0,
        )
    )
    assert c.interview_to_offer == 0.5
    assert c.offer_to_acceptance == 0.5


def test_funnel_to_dict_keys() -> None:
    from jobforge.analytics import FunnelReport

    r = FunnelReport(
        stages=FunnelStages(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
        conversions=ConversionRates(0.1, 0.2, 0.3, 0.4, 0.5),
    )
    d = funnel_to_dict(r)
    assert set(d.keys()) == {"stages", "conversions"}
    assert set(d["stages"].keys()) == {
        "jobs_discovered",
        "jobs_saved",
        "applications_created",
        "applications_submitted",
        "messages_sent",
        "recruiter_replies",
        "interviews_scheduled",
        "interviews_completed",
        "offers_received",
        "offers_accepted",
        "rejections",
    }
    assert set(d["conversions"].keys()) == {
        "discovery_to_apply",
        "apply_to_reply",
        "apply_to_interview",
        "interview_to_offer",
        "offer_to_acceptance",
    }


def test_stages_to_dict_keys() -> None:
    s = FunnelStages(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    d = stages_to_dict(s)
    assert d["jobs_discovered"] == 1
    assert d["offers_accepted"] == 10


def test_conversions_to_dict_keys() -> None:
    c = ConversionRates(0.1, 0.2, 0.3, 0.4, 0.5)
    d = conversions_to_dict(c)
    assert d["discovery_to_apply"] == 0.1
    assert d["offer_to_acceptance"] == 0.5


# ---------------- compute_stages (DB) ----------------


async def test_compute_stages_empty() -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    # Clear discovered_jobs to make jobs_discovered deterministic.
    async with session_scope() as session:
        await session.execute(delete(DiscoveredJob))
    s = await compute_stages(user_id)
    assert s.applications_created == 0
    assert s.applications_submitted == 0
    assert s.interviews_scheduled == 0
    assert s.offers_received == 0


async def test_compute_stages_counts_applications_submitted_cumulatively() -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    app = await create_application(
        user_id,
        CreateApplicationRequest(company="Acme", title="Eng"),
    )
    await update_status(user_id, app.id, StatusUpdateRequest(to_status="applied"))
    await update_status(
        user_id, app.id, StatusUpdateRequest(to_status="rejected")
    )
    s = await compute_stages(user_id)
    # The app moved applied → rejected, but applications_submitted is cumulative.
    assert s.applications_submitted == 1


async def test_compute_stages_counts_interviews_after_completed() -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    app = await create_application(
        user_id,
        CreateApplicationRequest(company="Acme", title="Eng"),
    )
    for st in ("applied", "interview_scheduled", "interview_completed"):
        await update_status(user_id, app.id, StatusUpdateRequest(to_status=st))
    s = await compute_stages(user_id)
    assert s.interviews_scheduled == 1
    assert s.interviews_completed == 1


async def test_compute_stages_counts_offers_and_acceptances() -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    app = await create_application(
        user_id,
        CreateApplicationRequest(company="Acme", title="Eng"),
    )
    for st in (
        "applied",
        "interview_scheduled",
        "interview_completed",
        "offer",
        "accepted",
    ):
        await update_status(user_id, app.id, StatusUpdateRequest(to_status=st))
    s = await compute_stages(user_id)
    assert s.offers_received == 1
    assert s.offers_accepted == 1


async def test_compute_stages_counts_rejections_via_current_status() -> None:
    user_id = USER_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    app = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    await update_status(user_id, app.id, StatusUpdateRequest(to_status="rejected"))
    s = await compute_stages(user_id)
    assert s.rejections == 1


async def test_compute_stages_jobs_saved_only_current_state() -> None:
    user_id = USER_BASE + 6
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await create_application(
        user_id, CreateApplicationRequest(company="A", title="T")
    )
    await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    b = await create_application(
        user_id, CreateApplicationRequest(company="B", title="T")
    )
    _ = b
    s = await compute_stages(user_id)
    # Only `b` is currently saved.
    assert s.jobs_saved == 1


async def test_compute_stages_messages_sent_from_outreach_events() -> None:
    user_id = USER_BASE + 7
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=contact.id))
    await update_outreach_status(
        user_id, camp.id, __import__("jobforge.outreach", fromlist=["StatusUpdateRequest"]).StatusUpdateRequest(to_status=O_SENT)
    )
    s = await compute_stages(user_id)
    assert s.messages_sent == 1


async def test_compute_stages_recruiter_replies_from_outreach_events() -> None:
    user_id = USER_BASE + 8
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=contact.id))
    from jobforge.outreach import StatusUpdateRequest as OutreachStatusReq

    await update_outreach_status(
        user_id, camp.id, OutreachStatusReq(to_status=O_SENT)
    )
    await update_outreach_status(
        user_id, camp.id, OutreachStatusReq(to_status=O_REPLIED)
    )
    s = await compute_stages(user_id)
    assert s.messages_sent == 1
    assert s.recruiter_replies == 1


async def test_compute_funnel_combines_stages_and_conversions() -> None:
    user_id = USER_BASE + 9
    await _ensure_user(user_id)
    await _wipe(user_id)
    app = await create_application(
        user_id, CreateApplicationRequest(company="Acme", title="Eng")
    )
    for st in ("applied", "interview_scheduled", "interview_completed"):
        await update_status(user_id, app.id, StatusUpdateRequest(to_status=st))
    report = await compute_funnel(user_id)
    assert report.stages.applications_submitted == 1
    assert report.stages.interviews_scheduled == 1
    assert report.conversions.apply_to_interview == 1.0
    assert report.conversions.interview_to_offer == 0.0


async def test_compute_stages_users_are_isolated() -> None:
    user_a = USER_BASE + 10
    user_b = USER_BASE + 11
    await _ensure_user(user_a)
    await _ensure_user(user_b)
    await _wipe(user_a)
    await _wipe(user_b)
    app = await create_application(
        user_a, CreateApplicationRequest(company="Acme", title="Eng")
    )
    await update_status(user_a, app.id, StatusUpdateRequest(to_status="applied"))
    a = await compute_stages(user_a)
    b = await compute_stages(user_b)
    assert a.applications_submitted == 1
    assert b.applications_submitted == 0


async def test_compute_funnel_outreach_interview_status_counts_toward_messages_sent() -> None:
    user_id = USER_BASE + 12
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=contact.id))
    from jobforge.outreach import StatusUpdateRequest as OutreachStatusReq

    for st in (O_SENT, O_REPLIED, O_INTERVIEW):
        await update_outreach_status(
            user_id, camp.id, OutreachStatusReq(to_status=st)
        )
    s = await compute_stages(user_id)
    assert s.messages_sent == 1
    assert s.recruiter_replies == 1


def _utc_today() -> datetime:
    return datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
