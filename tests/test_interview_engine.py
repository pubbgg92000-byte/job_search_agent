"""Engine + persistence tests for the interview prep generator.

Uses the same async DB pattern as `test_applications.py` (no TestClient).
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from jobforge.applications import ApplicationError
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    CompanyProfile,
    InterviewPlan,
    InterviewQuestion,
    InterviewStudyPlan,
    Profile,
    User,
)
from jobforge.db.session import session_scope
from jobforge.interview import (
    generate_plan,
    generate_questions,
    generate_study_plan,
    get_plan,
    latest_plan_for_application,
    list_plans_for_application,
    list_questions,
    list_study_plans,
    plan_to_dict,
    question_to_dict,
    study_plan_to_dict,
)
from jobforge.interview.questions import (
    CATEGORY_BEHAVIORAL,
    CATEGORY_TECHNICAL,
    DIFFICULTY_HARD,
)

USER_ID_BASE = 86000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(
                User(id=user_id, name="Interview Test", email=f"int-{user_id}@x.test")
            )


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        ids = (
            await session.execute(
                Application.__table__.select().where(Application.user_id == user_id)
            )
        ).all()
        app_ids = [r.id for r in ids]
        if app_ids:
            plan_rows = (
                await session.execute(
                    InterviewPlan.__table__.select().where(
                        InterviewPlan.application_id.in_(app_ids)
                    )
                )
            ).all()
            plan_ids = [r.id for r in plan_rows]
            if plan_ids:
                await session.execute(
                    delete(InterviewQuestion).where(
                        InterviewQuestion.plan_id.in_(plan_ids)
                    )
                )
                await session.execute(
                    delete(InterviewStudyPlan).where(
                        InterviewStudyPlan.plan_id.in_(plan_ids)
                    )
                )
                await session.execute(
                    delete(InterviewPlan).where(InterviewPlan.id.in_(plan_ids))
                )
            await session.execute(
                delete(ApplicationEvent).where(
                    ApplicationEvent.application_id.in_(app_ids)
                )
            )
            await session.execute(
                delete(Application).where(Application.id.in_(app_ids))
            )
        await session.execute(delete(Profile).where(Profile.user_id == user_id))


async def _seed_application(
    user_id: int, company: str = "TestCo", title: str = "Senior Backend Engineer"
) -> int:
    async with session_scope() as session:
        app = Application(
            user_id=user_id,
            company=company,
            title=title,
            url="https://test.example/job/1",
            source="manual",
            status="saved",
        )
        session.add(app)
        await session.flush()
        return app.id


async def _seed_profile(user_id: int, skills: list[str] | None = None) -> None:
    async with session_scope() as session:
        session.add(
            Profile(
                user_id=user_id,
                source_filename="seed.pdf",
                raw_resume_text="Python PostgreSQL",
                parsed_json={
                    "name": "Test User",
                    "email": "test@x.test",
                    "skills": skills or ["Python", "PostgreSQL", "TypeScript"],
                    "experience": [
                        {"title": "Senior Software Engineer", "company": "PrevCo", "bullets": []}
                    ],
                },
            )
        )


async def _seed_company(name: str = "TestCo") -> None:
    async with session_scope() as session:
        existing = (
            await session.execute(
                CompanyProfile.__table__.select().where(CompanyProfile.name == name)
            )
        ).first()
        if existing:
            return
        session.add(
            CompanyProfile(
                name=name,
                industry="fintech",
                company_size="201-500",
                funding_stage="series_b",
                remote_policy="remote_first",
                growth_score=70,
                risk_score=20,
                summary=f"{name} is a fintech startup.",
                raw_signals={"phase3b": {"tech_stack": ["Python", "PostgreSQL"]}},
            )
        )


# ---------------- generate_plan ----------------


async def test_generate_plan_persists_row_and_returns_dto() -> None:
    user_id = USER_ID_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)

    dto = await generate_plan(user_id, app_id)
    assert dto.id is not None
    assert dto.application_id == app_id
    assert dto.difficulty in ("easy", "medium", "hard", "very_hard")
    assert 0 <= dto.confidence_score <= 100
    assert len(dto.stages) >= 3


async def test_generate_plan_without_persist_returns_dto_without_id() -> None:
    user_id = USER_ID_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)

    dto = await generate_plan(user_id, app_id, persist=False)
    assert dto.id is None
    plans = await list_plans_for_application(app_id)
    assert plans == []


async def test_generate_plan_uses_company_profile_when_present() -> None:
    user_id = USER_ID_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    await _seed_company("MidCorp")
    app_id = await _seed_application(user_id, company="MidCorp", title="Senior Engineer")

    dto = await generate_plan(user_id, app_id)
    joined = "\n".join(dto.company_prep)
    assert "MidCorp" in joined
    # MidCorp is 201-500 => "mid" class.
    assert dto.difficulty in ("medium", "hard")


async def test_generate_plan_no_application_raises() -> None:
    user_id = USER_ID_BASE + 4
    await _ensure_user(user_id)
    with pytest.raises(ApplicationError):
        await generate_plan(user_id, 999_999)


async def test_generate_plan_no_profile_still_works() -> None:
    user_id = USER_ID_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    app_id = await _seed_application(user_id)
    dto = await generate_plan(user_id, app_id)
    # No skills = nothing matched, but the engine should still produce stages.
    assert len(dto.stages) > 0


async def test_generate_plan_with_llm_notes_stores_notes() -> None:
    user_id = USER_ID_BASE + 6
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)

    dto = await generate_plan(user_id, app_id, llm_notes="- focus on TS")
    assert dto.notes == "- focus on TS"
    fetched = await get_plan(dto.id)
    assert fetched is not None
    assert fetched.notes == "- focus on TS"


async def test_latest_plan_for_application_returns_most_recent() -> None:
    user_id = USER_ID_BASE + 7
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    a = await generate_plan(user_id, app_id)
    b = await generate_plan(user_id, app_id)
    latest = await latest_plan_for_application(app_id)
    assert latest is not None
    assert latest.id == b.id
    assert latest.id != a.id


async def test_list_plans_orders_by_generated_at_desc() -> None:
    user_id = USER_ID_BASE + 8
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    await generate_plan(user_id, app_id)
    await generate_plan(user_id, app_id)
    plans = await list_plans_for_application(app_id)
    assert len(plans) == 2
    assert plans[0].id is not None
    assert plans[1].id is not None
    assert plans[0].id > plans[1].id


async def test_plan_to_dict_round_trips() -> None:
    user_id = USER_ID_BASE + 9
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    dto = await generate_plan(user_id, app_id)
    d = plan_to_dict(dto)
    expected = {
        "id", "application_id", "stages", "technical_topics",
        "behavioral_topics", "company_prep", "difficulty",
        "confidence_score", "risk_areas", "strengths", "notes",
        "generated_at", "matched_skills", "missing_skills",
    }
    assert expected <= set(d.keys())


# ---------------- generate_questions ----------------


async def test_generate_questions_persists_and_returns_full_bank() -> None:
    user_id = USER_ID_BASE + 10
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)

    questions = await generate_questions(plan.id, technical_topics=["postgresql"])
    assert len(questions) >= 15
    assert all(q.id is not None for q in questions)


async def test_generate_questions_with_persist_false_returns_unsaved() -> None:
    user_id = USER_ID_BASE + 11
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    questions = await generate_questions(
        plan.id, technical_topics=[], persist=False
    )
    assert all(q.id is None for q in questions)
    saved = await list_questions(plan.id)
    assert saved == []


async def test_generate_questions_unknown_plan_raises() -> None:
    with pytest.raises(ApplicationError):
        await generate_questions(999_999, technical_topics=[])


async def test_list_questions_filters_by_category() -> None:
    user_id = USER_ID_BASE + 12
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    await generate_questions(plan.id, technical_topics=[])
    behavioral = await list_questions(plan.id, category=CATEGORY_BEHAVIORAL)
    assert behavioral
    assert all(q.category == CATEGORY_BEHAVIORAL for q in behavioral)
    technical = await list_questions(plan.id, category=CATEGORY_TECHNICAL)
    assert technical
    assert all(q.category == CATEGORY_TECHNICAL for q in technical)


async def test_list_questions_filters_by_difficulty() -> None:
    user_id = USER_ID_BASE + 13
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    await generate_questions(plan.id, technical_topics=[])
    hard = await list_questions(plan.id, difficulty=DIFFICULTY_HARD)
    assert hard
    assert all(q.difficulty == DIFFICULTY_HARD for q in hard)


async def test_question_to_dict_keys() -> None:
    user_id = USER_ID_BASE + 14
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    qs = await generate_questions(plan.id, technical_topics=[])
    d = question_to_dict(qs[0])
    expected = {"id", "plan_id", "category", "topic", "difficulty", "prompt", "answer_outline"}
    assert set(d.keys()) == expected


# ---------------- generate_study_plan ----------------


async def test_generate_study_plan_persists_blocks() -> None:
    user_id = USER_ID_BASE + 15
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    sp = await generate_study_plan(
        plan.id,
        horizon_days=7,
        weakness_topics=["Rust"],
        interview_topics=["Postgres"],
        company="TestCo",
    )
    assert sp.id is not None
    assert sp.horizon_days == 7
    assert len(sp.blocks) == 8


async def test_generate_study_plan_replaces_same_horizon() -> None:
    user_id = USER_ID_BASE + 16
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    a = await generate_study_plan(
        plan.id, horizon_days=3, weakness_topics=[], interview_topics=[], company=None,
    )
    b = await generate_study_plan(
        plan.id, horizon_days=3, weakness_topics=[], interview_topics=[], company=None,
    )
    plans = await list_study_plans(plan.id)
    assert len(plans) == 1
    assert plans[0].id == b.id
    assert plans[0].id != a.id


async def test_generate_study_plan_unsupported_horizon_raises() -> None:
    user_id = USER_ID_BASE + 17
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    with pytest.raises(ApplicationError):
        await generate_study_plan(
            plan.id,
            horizon_days=5,
            weakness_topics=[],
            interview_topics=[],
            company=None,
        )


async def test_generate_study_plan_unknown_plan_raises() -> None:
    with pytest.raises(ApplicationError):
        await generate_study_plan(
            999_999,
            horizon_days=7,
            weakness_topics=[],
            interview_topics=[],
            company=None,
        )


async def test_list_study_plans_orders_by_horizon_asc() -> None:
    user_id = USER_ID_BASE + 18
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    await generate_study_plan(
        plan.id, horizon_days=14, weakness_topics=[], interview_topics=[], company=None,
    )
    await generate_study_plan(
        plan.id, horizon_days=1, weakness_topics=[], interview_topics=[], company=None,
    )
    await generate_study_plan(
        plan.id, horizon_days=7, weakness_topics=[], interview_topics=[], company=None,
    )
    plans = await list_study_plans(plan.id)
    horizons = [p.horizon_days for p in plans]
    assert horizons == sorted(horizons)


async def test_study_plan_to_dict_keys() -> None:
    user_id = USER_ID_BASE + 19
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    sp = await generate_study_plan(
        plan.id, horizon_days=1, weakness_topics=[], interview_topics=[], company=None,
    )
    d = study_plan_to_dict(sp)
    expected = {"id", "plan_id", "horizon_days", "total_hours", "blocks", "generated_at"}
    assert set(d.keys()) == expected


async def test_generate_study_plan_no_persist_returns_unsaved() -> None:
    user_id = USER_ID_BASE + 20
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    plan = await generate_plan(user_id, app_id)
    sp = await generate_study_plan(
        plan.id,
        horizon_days=7,
        weakness_topics=[],
        interview_topics=[],
        company=None,
        persist=False,
    )
    assert sp.id is None
    assert await list_study_plans(plan.id) == []


# ---------------- get_plan retrieval ----------------


async def test_get_plan_returns_none_for_unknown_id() -> None:
    assert await get_plan(999_999) is None


async def test_get_plan_returns_persisted_row() -> None:
    user_id = USER_ID_BASE + 21
    await _ensure_user(user_id)
    await _wipe(user_id)
    await _seed_profile(user_id)
    app_id = await _seed_application(user_id)
    dto = await generate_plan(user_id, app_id)
    fetched = await get_plan(dto.id)
    assert fetched is not None
    assert fetched.application_id == app_id
    assert fetched.difficulty == dto.difficulty
