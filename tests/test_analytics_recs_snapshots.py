"""Recommendation rules + snapshot persistence tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from jobforge.analytics import (
    build_recommendations,
    list_snapshots,
    recommendation_to_dict,
    recommendations_to_dict,
    record_daily_snapshot,
    snapshot_to_dict,
)
from jobforge.analytics.snapshots import _day_bounds
from jobforge.applications import (
    CreateApplicationRequest,
    StatusUpdateRequest,
    create_application,
    update_status,
)
from jobforge.db.models import (
    AnalyticsSnapshot,
    Application,
    ApplicationEvent,
    MessageEvent,
    OutreachCampaign,
    Profile,
    RecruiterContact,
    RecruiterMessage,
    SkillGapSnapshot,
    TailoredArtifact,
    User,
)
from jobforge.db.session import session_scope
from jobforge.outreach import (
    CreateCampaignRequest,
    DraftMessageRequest,
    MessageContext,
    UpsertContactRequest,
    create_campaign,
    draft_message,
    upsert_contact,
)
from jobforge.outreach import (
    StatusUpdateRequest as OutreachStatusReq,
)
from jobforge.outreach import (
    update_status as update_outreach_status,
)
from jobforge.outreach.status import (
    STATUS_REPLIED as O_REPLIED,
)
from jobforge.outreach.status import (
    STATUS_SENT as O_SENT,
)

USER_BASE = 96000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Recs", email=f"recs-{user_id}@x.test"))


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
            delete(SkillGapSnapshot).where(SkillGapSnapshot.user_id == user_id)
        )
        await session.execute(
            delete(TailoredArtifact).where(TailoredArtifact.user_id == user_id)
        )
        await session.execute(delete(Profile).where(Profile.user_id == user_id))
        await session.execute(
            delete(AnalyticsSnapshot).where(AnalyticsSnapshot.user_id == user_id)
        )


def _ctx():
    return MessageContext(
        company="Acme",
        contact_name="Sam",
        role_title="Engineer",
        matched_skills=["Python"],
    )


# ---------------- build_recommendations ----------------


async def test_recommendations_empty_for_no_data() -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await build_recommendations(user_id)
    assert r.items == []


async def test_recommendations_returns_baseline_when_some_data_but_no_trends() -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    await create_application(
        user_id, CreateApplicationRequest(company="C", title="E")
    )
    r = await build_recommendations(user_id)
    assert any(rec.kind == "general" for rec in r.items)


async def test_recommendations_includes_source_when_one_wins() -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    # 4 lever apps with 2 interviews vs 4 greenhouse apps with 0
    for i in range(4):
        a = await create_application(
            user_id,
            CreateApplicationRequest(company=f"L{i}", title="E", source="lever"),
        )
        sts = ["applied"]
        if i < 2:
            sts.append("interview_scheduled")
        for s in sts:
            await update_status(user_id, a.id, StatusUpdateRequest(to_status=s))
    for i in range(4):
        a = await create_application(
            user_id,
            CreateApplicationRequest(
                company=f"G{i}", title="E", source="greenhouse"
            ),
        )
        await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    r = await build_recommendations(user_id)
    kinds = {x.kind for x in r.items}
    assert "source" in kinds


async def test_recommendations_skill_rec_uses_latest_snapshot() -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    await create_application(
        user_id, CreateApplicationRequest(company="C", title="E")
    )
    async with session_scope() as session:
        session.add(
            SkillGapSnapshot(
                user_id=user_id,
                profile_id=None,
                jobs_considered=80,
                gaps_json={
                    "top_gaps": [
                        {"skill": "Rust", "importance_score": 80, "frequency": 12},
                        {"skill": "Kafka", "importance_score": 75, "frequency": 6},
                    ]
                },
                computed_at=datetime.now(UTC),
            )
        )
    r = await build_recommendations(user_id)
    skill = next((x for x in r.items if x.kind == "skill"), None)
    assert skill is not None
    assert "Rust" in skill.title


async def test_recommendations_company_when_one_company_has_interviews() -> None:
    user_id = USER_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await create_application(
        user_id, CreateApplicationRequest(company="BigCo", title="E")
    )
    for st in ("applied", "interview_scheduled"):
        await update_status(user_id, a.id, StatusUpdateRequest(to_status=st))
    r = await build_recommendations(user_id)
    company = next((x for x in r.items if x.kind == "company"), None)
    assert company is not None
    assert "BigCo" in company.title


async def test_recommendations_resume_when_a_variant_outperforms() -> None:
    user_id = USER_BASE + 6
    await _ensure_user(user_id)
    await _wipe(user_id)
    async with session_scope() as session:
        from jobforge.db.models import Job

        profile = Profile(
            user_id=user_id,
            source_filename="x.pdf",
            raw_resume_text="X",
            parsed_json={"skills": ["Python"]},
        )
        session.add(profile)
        await session.flush()
        job = Job(user_id=user_id, raw_jd_text="x", company="C", title="T")
        session.add(job)
        await session.flush()
        art = TailoredArtifact(
            user_id=user_id,
            job_id=job.id,
            profile_id=profile.id,
            tailored_resume_md="md",
            ats_score=90,
            model_used="claude-opus",
        )
        session.add(art)
        await session.flush()
        art_id = art.id

    for i in range(4):
        a = await create_application(
            user_id,
            CreateApplicationRequest(
                company=f"C{i}", title="E", artifact_id=art_id
            ),
        )
        sts = ["applied"]
        if i < 2:
            sts.append("interview_scheduled")
        for s in sts:
            await update_status(user_id, a.id, StatusUpdateRequest(to_status=s))
    r = await build_recommendations(user_id)
    resume = next((x for x in r.items if x.kind == "resume"), None)
    assert resume is not None
    assert "variant" in resume.title.lower()


async def test_recommendations_to_dict_keys() -> None:
    user_id = USER_BASE + 7
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await build_recommendations(user_id)
    d = recommendations_to_dict(r)
    assert set(d.keys()) == {"items", "total"}


async def test_recommendation_to_dict_carries_extras() -> None:
    from jobforge.analytics import Recommendation

    r = Recommendation(
        kind="source", title="x", detail="y", confidence="high", extra={"a": 1}
    )
    d = recommendation_to_dict(r)
    assert d["extra"] == {"a": 1}
    assert d["confidence"] == "high"


async def test_recommendations_outreach_follow_up_lift_recommendation() -> None:
    user_id = USER_BASE + 8
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    # 2 campaigns with follow-up + reply, 1 without + ignored
    for _ in range(2):
        camp = await create_campaign(
            user_id, CreateCampaignRequest(contact_id=contact.id)
        )
        await draft_message(
            user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
        )
        await draft_message(
            user_id, camp.id, DraftMessageRequest(kind="follow_up", ctx=_ctx())
        )
        await update_outreach_status(
            user_id, camp.id, OutreachStatusReq(to_status=O_SENT)
        )
        await update_outreach_status(
            user_id, camp.id, OutreachStatusReq(to_status=O_REPLIED)
        )
    no_camp = await create_campaign(
        user_id, CreateCampaignRequest(contact_id=contact.id)
    )
    await draft_message(
        user_id, no_camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
    )
    await update_outreach_status(
        user_id, no_camp.id, OutreachStatusReq(to_status=O_SENT)
    )
    await update_outreach_status(
        user_id, no_camp.id, OutreachStatusReq(to_status="ignored")
    )
    r = await build_recommendations(user_id)
    out_rec = next((x for x in r.items if x.kind == "outreach"), None)
    assert out_rec is not None


# ---------------- snapshots ----------------


async def test_record_snapshot_creates_row() -> None:
    user_id = USER_BASE + 20
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await record_daily_snapshot(user_id)
    assert row.id is not None
    snaps = await list_snapshots(user_id)
    assert len(snaps) == 1


async def test_record_snapshot_idempotent_on_same_day() -> None:
    user_id = USER_BASE + 21
    await _ensure_user(user_id)
    await _wipe(user_id)
    now = datetime.now(UTC)
    a = await record_daily_snapshot(user_id, now=now)
    b = await record_daily_snapshot(user_id, now=now)
    assert a.id == b.id


async def test_record_snapshot_updates_existing_row() -> None:
    user_id = USER_BASE + 22
    await _ensure_user(user_id)
    await _wipe(user_id)
    now = datetime.now(UTC)
    await record_daily_snapshot(user_id, now=now)
    app = await create_application(
        user_id, CreateApplicationRequest(company="C", title="E")
    )
    await update_status(user_id, app.id, StatusUpdateRequest(to_status="applied"))
    updated = await record_daily_snapshot(user_id, now=now)
    assert updated.applications_submitted == 1


async def test_record_snapshot_creates_new_row_for_different_day() -> None:
    user_id = USER_BASE + 23
    await _ensure_user(user_id)
    await _wipe(user_id)
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)
    a = await record_daily_snapshot(user_id, now=yesterday)
    b = await record_daily_snapshot(user_id, now=today)
    assert a.id != b.id


async def test_list_snapshots_orders_chronologically() -> None:
    user_id = USER_BASE + 24
    await _ensure_user(user_id)
    await _wipe(user_id)
    now = datetime.now(UTC)
    for d in (3, 1, 2):
        await record_daily_snapshot(user_id, now=now - timedelta(days=d))
    snaps = await list_snapshots(user_id, limit=10)
    dates = [s.snapshot_date for s in snaps]
    assert dates == sorted(dates)


async def test_list_snapshots_respects_limit() -> None:
    user_id = USER_BASE + 25
    await _ensure_user(user_id)
    await _wipe(user_id)
    now = datetime.now(UTC)
    for d in range(5):
        await record_daily_snapshot(user_id, now=now - timedelta(days=d))
    snaps = await list_snapshots(user_id, limit=2)
    assert len(snaps) == 2


def test_day_bounds_truncates_to_midnight_utc() -> None:
    when = datetime(2026, 6, 8, 15, 32, 5, tzinfo=UTC)
    out = _day_bounds(when)
    assert out.hour == 0
    assert out.minute == 0
    assert out.second == 0


async def test_snapshot_to_dict_keys() -> None:
    user_id = USER_BASE + 26
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await record_daily_snapshot(user_id)
    d = snapshot_to_dict(row)
    expected = {
        "id", "snapshot_date", "jobs_discovered", "jobs_saved",
        "applications_created", "applications_submitted",
        "messages_sent", "recruiter_replies",
        "interviews_scheduled", "interviews_completed",
        "offers_received", "offers_accepted", "rejections",
    }
    assert set(d.keys()) == expected
