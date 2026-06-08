"""Source / resume / outreach / company analytics tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from jobforge.analytics import (
    SUPPORTED_SOURCES,
    compute_outreach_report,
    compute_resume_report,
    compute_source_report,
    outreach_report_to_dict,
    resume_report_to_dict,
    skill_gap_trend,
    source_report_to_dict,
    top_companies_by_interviews,
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
from jobforge.outreach.status import STATUS_REPLIED as O_REPLIED
from jobforge.outreach.status import STATUS_SENT as O_SENT

USER_BASE = 95000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Reports", email=f"r-{user_id}@x.test"))


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


# ---------------- compute_source_report ----------------


async def test_source_report_includes_all_supported_sources_even_with_zero() -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_source_report(user_id)
    keys = {row.source for row in r.rows}
    assert set(SUPPORTED_SOURCES).issubset(keys)


async def test_source_report_counts_applications_per_source() -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    for src in ("greenhouse", "lever", "greenhouse"):
        app = await create_application(
            user_id,
            CreateApplicationRequest(company="C", title="E", source=src),
        )
        await update_status(user_id, app.id, StatusUpdateRequest(to_status="applied"))
    r = await compute_source_report(user_id)
    by_source = {row.source: row for row in r.rows}
    assert by_source["greenhouse"].applications == 2
    assert by_source["lever"].applications == 1


async def test_source_report_counts_interviews() -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await create_application(
        user_id,
        CreateApplicationRequest(company="C", title="E", source="ashby"),
    )
    for st in ("applied", "interview_scheduled"):
        await update_status(user_id, a.id, StatusUpdateRequest(to_status=st))
    r = await compute_source_report(user_id)
    by_source = {row.source: row for row in r.rows}
    assert by_source["ashby"].interviews == 1


async def test_source_report_picks_best_source_by_interview_rate() -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    # greenhouse: 2 apps, 0 interviews; lever: 1 app, 1 interview
    for _ in range(2):
        a = await create_application(
            user_id,
            CreateApplicationRequest(company="C", title="E", source="greenhouse"),
        )
        await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    b = await create_application(
        user_id,
        CreateApplicationRequest(company="C", title="E", source="lever"),
    )
    for st in ("applied", "interview_scheduled"):
        await update_status(user_id, b.id, StatusUpdateRequest(to_status=st))
    r = await compute_source_report(user_id)
    assert r.best_source_for_interviews == "lever"


async def test_source_report_no_data_returns_none_best_source() -> None:
    user_id = USER_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_source_report(user_id)
    assert r.best_source_for_interviews is None


async def test_source_report_handles_manual_source() -> None:
    user_id = USER_BASE + 6
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await create_application(
        user_id,
        CreateApplicationRequest(company="C", title="E", source="manual"),
    )
    await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    r = await compute_source_report(user_id)
    by_source = {row.source: row for row in r.rows}
    assert by_source["manual"].applications == 1


async def test_source_report_to_dict_keys() -> None:
    user_id = USER_BASE + 7
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_source_report(user_id)
    d = source_report_to_dict(r)
    assert set(d.keys()) == {
        "total_applications",
        "best_source_for_interviews",
        "rows",
    }


async def test_source_row_rates_use_application_denominator() -> None:
    user_id = USER_BASE + 8
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await create_application(
        user_id,
        CreateApplicationRequest(company="C", title="E", source="remoteok"),
    )
    for st in ("applied", "interview_scheduled"):
        await update_status(user_id, a.id, StatusUpdateRequest(to_status=st))
    r = await compute_source_report(user_id)
    row = next(x for x in r.rows if x.source == "remoteok")
    assert row.interview_rate == 1.0
    assert row.offer_rate == 0.0


# ---------------- compute_resume_report ----------------


async def _seed_profile(user_id: int) -> int:
    async with session_scope() as session:
        p = Profile(
            user_id=user_id,
            source_filename="x.pdf",
            raw_resume_text="X",
            parsed_json={"skills": ["Python"]},
        )
        session.add(p)
        await session.flush()
        return p.id


async def _seed_artifact(
    user_id: int, profile_id: int, *, model_used: str, ats_score: int
) -> int:
    async with session_scope() as session:
        # We need a Job row for FK — fabricate one.
        from jobforge.db.models import Job

        job = Job(
            user_id=user_id,
            raw_jd_text="x",
            company="C",
            title="T",
        )
        session.add(job)
        await session.flush()
        art = TailoredArtifact(
            user_id=user_id,
            job_id=job.id,
            profile_id=profile_id,
            tailored_resume_md="md",
            ats_score=ats_score,
            model_used=model_used,
        )
        session.add(art)
        await session.flush()
        return art.id


async def test_resume_report_empty() -> None:
    user_id = USER_BASE + 20
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_resume_report(user_id)
    assert r.total_artifacts == 0
    assert r.top_performing_artifact is None


async def test_resume_report_counts_applications_per_artifact() -> None:
    user_id = USER_BASE + 21
    await _ensure_user(user_id)
    await _wipe(user_id)
    pid = await _seed_profile(user_id)
    art_id = await _seed_artifact(
        user_id, pid, model_used="claude-sonnet", ats_score=80
    )
    for _ in range(2):
        await create_application(
            user_id,
            CreateApplicationRequest(
                company="C", title="E", artifact_id=art_id
            ),
        )
    r = await compute_resume_report(user_id)
    assert r.total_artifacts == 1
    assert r.rows[0].applications == 2


async def test_resume_report_top_artifact_by_interview_rate() -> None:
    user_id = USER_BASE + 22
    await _ensure_user(user_id)
    await _wipe(user_id)
    pid = await _seed_profile(user_id)
    win_id = await _seed_artifact(
        user_id, pid, model_used="claude-opus", ats_score=92
    )
    lose_id = await _seed_artifact(
        user_id, pid, model_used="claude-haiku", ats_score=70
    )

    # win artifact: 3 apps, 2 interviews
    for i in range(3):
        a = await create_application(
            user_id,
            CreateApplicationRequest(
                company=f"C{i}", title="E", artifact_id=win_id
            ),
        )
        if i < 2:
            for st in ("applied", "interview_scheduled"):
                await update_status(user_id, a.id, StatusUpdateRequest(to_status=st))
        else:
            await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))

    # lose artifact: 5 apps, 1 interview
    for i in range(5):
        a = await create_application(
            user_id,
            CreateApplicationRequest(
                company=f"D{i}", title="E", artifact_id=lose_id
            ),
        )
        if i == 0:
            for st in ("applied", "interview_scheduled"):
                await update_status(user_id, a.id, StatusUpdateRequest(to_status=st))
        else:
            await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))

    r = await compute_resume_report(user_id)
    assert r.top_performing_artifact is not None
    assert r.top_performing_artifact.artifact_id == win_id


async def test_resume_report_to_dict_keys() -> None:
    user_id = USER_BASE + 23
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_resume_report(user_id)
    d = resume_report_to_dict(r)
    assert set(d.keys()) == {"total_artifacts", "top_performing_artifact", "rows"}


async def test_resume_row_interview_rate_zero_for_zero_applications() -> None:
    user_id = USER_BASE + 24
    await _ensure_user(user_id)
    await _wipe(user_id)
    pid = await _seed_profile(user_id)
    await _seed_artifact(user_id, pid, model_used="m", ats_score=50)
    r = await compute_resume_report(user_id)
    assert r.rows[0].interview_rate == 0.0


# ---------------- compute_outreach_report ----------------


def _ctx():
    return MessageContext(
        company="Acme",
        contact_name="Sam",
        role_title="Engineer",
        matched_skills=["Python"],
    )


async def test_outreach_report_empty_lists_all_kinds() -> None:
    user_id = USER_BASE + 30
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_outreach_report(user_id)
    kinds = {row.kind for row in r.by_kind}
    assert "initial_outreach" in kinds
    assert "follow_up" in kinds
    assert "thank_you" in kinds


async def test_outreach_report_counts_by_kind() -> None:
    user_id = USER_BASE + 31
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=contact.id))
    await draft_message(
        user_id,
        camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    await update_outreach_status(
        user_id, camp.id, OutreachStatusReq(to_status=O_SENT)
    )
    r = await compute_outreach_report(user_id)
    initial = next(row for row in r.by_kind if row.kind == "initial_outreach")
    assert initial.sent == 1


async def test_outreach_report_counts_by_company() -> None:
    user_id = USER_BASE + 32
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact_a = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    contact_b = await upsert_contact(
        user_id, UpsertContactRequest(company="Beta", name="Lee")
    )
    for c in (contact_a, contact_b):
        camp = await create_campaign(user_id, CreateCampaignRequest(contact_id=c.id))
        await draft_message(
            user_id, camp.id, DraftMessageRequest(kind="initial_outreach", ctx=_ctx())
        )
        await update_outreach_status(
            user_id, camp.id, OutreachStatusReq(to_status=O_SENT)
        )
    r = await compute_outreach_report(user_id)
    companies = {row.company for row in r.by_company}
    assert "Acme" in companies
    assert "Beta" in companies


async def test_outreach_report_follow_up_effectiveness_zero_when_no_followups() -> None:
    user_id = USER_BASE + 33
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_outreach_report(user_id)
    assert r.follow_up.campaigns_with_follow_up == 0
    assert r.follow_up.reply_rate_with_follow_up == 0.0


async def test_outreach_report_follow_up_lift_when_follow_ups_help() -> None:
    user_id = USER_BASE + 34
    await _ensure_user(user_id)
    await _wipe(user_id)
    contact = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    # Campaign with a follow-up message → replied
    with_camp = await create_campaign(
        user_id, CreateCampaignRequest(contact_id=contact.id)
    )
    await draft_message(
        user_id,
        with_camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    await draft_message(
        user_id,
        with_camp.id,
        DraftMessageRequest(kind="follow_up", ctx=_ctx()),
    )
    await update_outreach_status(
        user_id, with_camp.id, OutreachStatusReq(to_status=O_SENT)
    )
    await update_outreach_status(
        user_id, with_camp.id, OutreachStatusReq(to_status=O_REPLIED)
    )
    # Campaign without follow-up → ignored
    without_camp = await create_campaign(
        user_id, CreateCampaignRequest(contact_id=contact.id)
    )
    await draft_message(
        user_id,
        without_camp.id,
        DraftMessageRequest(kind="initial_outreach", ctx=_ctx()),
    )
    await update_outreach_status(
        user_id, without_camp.id, OutreachStatusReq(to_status=O_SENT)
    )
    await update_outreach_status(
        user_id, without_camp.id, OutreachStatusReq(to_status="ignored")
    )
    r = await compute_outreach_report(user_id)
    assert r.follow_up.campaigns_with_follow_up == 1
    assert r.follow_up.reply_rate_with_follow_up == 1.0
    assert r.follow_up.reply_rate_without_follow_up == 0.0
    assert r.follow_up.follow_up_lift == 1.0


async def test_outreach_report_to_dict_keys() -> None:
    user_id = USER_BASE + 35
    await _ensure_user(user_id)
    await _wipe(user_id)
    r = await compute_outreach_report(user_id)
    d = outreach_report_to_dict(r)
    assert set(d.keys()) == {"by_kind", "by_company", "follow_up"}


# ---------------- top_companies_by_interviews ----------------


async def test_top_companies_returns_empty_when_no_data() -> None:
    user_id = USER_BASE + 40
    await _ensure_user(user_id)
    await _wipe(user_id)
    rows = await top_companies_by_interviews(user_id)
    assert rows == []


async def test_top_companies_orders_by_interviews() -> None:
    user_id = USER_BASE + 41
    await _ensure_user(user_id)
    await _wipe(user_id)
    # CompanyA: 1 app, 0 interviews; CompanyB: 1 app, 1 interview
    a = await create_application(
        user_id, CreateApplicationRequest(company="CompanyA", title="E")
    )
    await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    b = await create_application(
        user_id, CreateApplicationRequest(company="CompanyB", title="E")
    )
    for st in ("applied", "interview_scheduled"):
        await update_status(user_id, b.id, StatusUpdateRequest(to_status=st))
    rows = await top_companies_by_interviews(user_id, limit=5)
    assert rows[0].company == "CompanyB"


async def test_top_companies_respects_limit() -> None:
    user_id = USER_BASE + 42
    await _ensure_user(user_id)
    await _wipe(user_id)
    for i in range(5):
        a = await create_application(
            user_id, CreateApplicationRequest(company=f"C{i}", title="E")
        )
        await update_status(user_id, a.id, StatusUpdateRequest(to_status="applied"))
    rows = await top_companies_by_interviews(user_id, limit=2)
    assert len(rows) == 2


# ---------------- skill_gap_trend ----------------


async def test_skill_gap_trend_empty_returns_no_points() -> None:
    user_id = USER_BASE + 50
    await _ensure_user(user_id)
    await _wipe(user_id)
    points = await skill_gap_trend(user_id)
    assert points == []


async def test_skill_gap_trend_orders_chronologically() -> None:
    user_id = USER_BASE + 51
    await _ensure_user(user_id)
    await _wipe(user_id)
    now = datetime.now(UTC)
    async with session_scope() as session:
        for i in range(3):
            session.add(
                SkillGapSnapshot(
                    user_id=user_id,
                    profile_id=None,
                    jobs_considered=10 + i,
                    gaps_json={
                        "top_gaps": [
                            {"skill": f"Skill{i}", "importance_score": 80, "frequency": 5}
                        ]
                    },
                    computed_at=now - timedelta(days=2 - i),
                )
            )
    points = await skill_gap_trend(user_id, limit_points=5)
    # Oldest first.
    job_counts = [p.jobs_considered for p in points]
    assert job_counts == [10, 11, 12]


async def test_skill_gap_trend_caps_skills_per_point() -> None:
    user_id = USER_BASE + 52
    await _ensure_user(user_id)
    await _wipe(user_id)
    big = [
        {"skill": f"S{i}", "importance_score": 100 - i, "frequency": 1}
        for i in range(20)
    ]
    async with session_scope() as session:
        session.add(
            SkillGapSnapshot(
                user_id=user_id,
                profile_id=None,
                jobs_considered=10,
                gaps_json={"top_gaps": big},
                computed_at=datetime.now(UTC),
            )
        )
    points = await skill_gap_trend(user_id)
    assert len(points) == 1
    assert len(points[0].top_skills) == 8


async def test_skill_gap_trend_skips_invalid_entries() -> None:
    user_id = USER_BASE + 53
    await _ensure_user(user_id)
    await _wipe(user_id)
    async with session_scope() as session:
        session.add(
            SkillGapSnapshot(
                user_id=user_id,
                profile_id=None,
                jobs_considered=1,
                gaps_json={
                    "top_gaps": [
                        {"skill": "Python", "importance_score": 80},
                        "not-a-dict",
                        {},  # missing skill name
                    ]
                },
                computed_at=datetime.now(UTC),
            )
        )
    points = await skill_gap_trend(user_id)
    assert len(points) == 1
    assert len(points[0].top_skills) == 1
