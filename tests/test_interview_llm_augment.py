"""LLM augmentation tests — every LLM call is mocked.

The augmenter is OPT-IN; the engine works fine without it. These tests
verify that when it is opted into, the output flows through to the plan
notes and never touches the network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from jobforge.db.models import (
    Application,
    ApplicationEvent,
    InterviewPlan,
    InterviewQuestion,
    InterviewStudyPlan,
    Profile,
    User,
)
from jobforge.db.session import session_scope
from jobforge.interview.engine import _build_plan, generate_plan
from jobforge.interview.heuristics import PlanInputs
from jobforge.interview.llm_augment import summarize_focus

USER_ID = 88001


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="LLM Test", email=f"llm-{user_id}@x.test"))


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
            await session.execute(delete(Application).where(Application.id.in_(app_ids)))
        await session.execute(delete(Profile).where(Profile.user_id == user_id))


async def _seed_application_and_profile(user_id: int) -> int:
    async with session_scope() as session:
        session.add(
            Profile(
                user_id=user_id,
                source_filename="seed.pdf",
                raw_resume_text="Python TypeScript",
                parsed_json={
                    "name": "LT",
                    "email": "lt@x.test",
                    "skills": ["Python", "TypeScript"],
                    "experience": [{"title": "Senior Engineer", "company": "P", "bullets": []}],
                },
            )
        )
        app = Application(
            user_id=user_id,
            company="Anthropic",
            title="Senior Backend Engineer",
            url="https://example/job",
            source="manual",
            status="saved",
        )
        session.add(app)
        await session.flush()
        return app.id


@pytest.fixture
def patched_llm():
    with patch(
        "jobforge.interview.llm_augment.call_text",
        new=AsyncMock(return_value="- Brush up on TypeScript\n- Practice system design"),
    ) as mock:
        yield mock


async def test_summarize_focus_uses_mocked_llm(patched_llm) -> None:
    inputs = PlanInputs(
        application={"id": 1, "company": "Anthropic", "title": "Engineer"},
        job_description="We use TypeScript and PostgreSQL.",
        profile={"skills": ["Python"]},
        company=None,
        missing_skills=["TypeScript"],
        matched_skills=["Python"],
        seniority="senior",
        company_class="startup",
    )
    out = await summarize_focus(inputs)
    assert "TypeScript" in out
    patched_llm.assert_called_once()


async def test_summarize_focus_passes_company_summary_to_prompt(patched_llm) -> None:
    inputs = PlanInputs(
        application={"id": 1, "company": "Anthropic", "title": "Engineer"},
        job_description="JD body",
        profile={},
        company={"summary": "AI safety company", "tech_stack": ["Python"]},
        missing_skills=[],
        matched_skills=[],
        seniority="mid",
        company_class="startup",
    )
    await summarize_focus(inputs)
    # The "user" prompt arg should contain the company summary.
    kwargs = patched_llm.call_args.kwargs
    assert "AI safety company" in kwargs["user"]


async def test_summarize_focus_handles_llm_failure_gracefully() -> None:
    with patch(
        "jobforge.interview.llm_augment.call_text",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        out = await summarize_focus(
            PlanInputs(
                application={"id": 1, "company": "X", "title": "E"},
                job_description="",
                profile={},
                company=None,
                missing_skills=[],
                matched_skills=[],
                seniority="mid",
                company_class="startup",
            )
        )
    assert out == ""


async def test_generate_plan_with_llm_notes_attaches_text(patched_llm) -> None:
    await _ensure_user(USER_ID)
    await _wipe(USER_ID)
    app_id = await _seed_application_and_profile(USER_ID)
    _, inputs = await _build_plan(USER_ID, app_id)
    notes = await summarize_focus(inputs)
    dto = await generate_plan(USER_ID, app_id, llm_notes=notes)
    assert dto.notes is not None
    assert "TypeScript" in dto.notes


async def test_build_plan_does_not_call_llm() -> None:
    """The deterministic path must not touch the LLM client at all."""
    await _ensure_user(USER_ID)
    await _wipe(USER_ID)
    app_id = await _seed_application_and_profile(USER_ID)
    with patch(
        "jobforge.llm.client.call_text", new=AsyncMock()
    ) as mock_text, patch(
        "jobforge.llm.client.call_structured", new=AsyncMock()
    ) as mock_struct:
        await generate_plan(USER_ID, app_id)
    mock_text.assert_not_called()
    mock_struct.assert_not_called()
