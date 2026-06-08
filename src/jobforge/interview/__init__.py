"""Interview intelligence agent — Phase 3C.

Top-level facade. The service layer (`engine.py`, `questions.py`,
`weakness.py`, `study_planner.py`) is deterministic and offline. LLM-backed
augmentation is opt-in via `llm_augment.py` and is mocked in every test.
"""
from __future__ import annotations

from jobforge.interview.engine import (
    InterviewPlanDTO,
    InterviewStage,
    RiskArea,
    generate_plan,
    get_plan,
    latest_plan_for_application,
    list_plans_for_application,
    plan_to_dict,
)
from jobforge.interview.questions import (
    QuestionDTO,
    generate_questions,
    list_questions,
    question_to_dict,
)
from jobforge.interview.study_planner import (
    StudyBlock,
    StudyPlanDTO,
    generate_study_plan,
    list_study_plans,
    pick_horizon_for_interview,
    study_plan_to_dict,
)
from jobforge.interview.weakness import (
    WeaknessReport,
    WeaknessRow,
    compute_weakness_report,
    weakness_report_to_dict,
)

__all__ = [
    "InterviewPlanDTO",
    "InterviewStage",
    "QuestionDTO",
    "RiskArea",
    "StudyBlock",
    "StudyPlanDTO",
    "WeaknessReport",
    "WeaknessRow",
    "compute_weakness_report",
    "generate_plan",
    "generate_questions",
    "generate_study_plan",
    "get_plan",
    "latest_plan_for_application",
    "list_plans_for_application",
    "list_questions",
    "list_study_plans",
    "pick_horizon_for_interview",
    "plan_to_dict",
    "question_to_dict",
    "study_plan_to_dict",
    "weakness_report_to_dict",
]
