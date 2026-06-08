"""Pure bank-generation tests for the question generator (no DB)."""
from __future__ import annotations

from jobforge.interview.questions import (
    ALL_DIFFICULTIES,
    CATEGORY_BEHAVIORAL,
    CATEGORY_SYSTEM_DESIGN,
    CATEGORY_TECHNICAL,
    DIFFICULTY_EASY,
    DIFFICULTY_HARD,
    DIFFICULTY_MEDIUM,
    generate_question_bank,
    topics_for_plan,
)


def test_topics_for_plan_always_includes_canonical_set() -> None:
    out = topics_for_plan(technical_topics=[])
    for canonical in ("node.js", "typescript", "postgresql", "system design"):
        assert canonical in out
    assert "behavioral" in out


def test_topics_for_plan_priority_first_then_canonical() -> None:
    out = topics_for_plan(technical_topics=["postgresql", "node.js"])
    # priority list should precede the unprioritised canonical names
    assert out.index("postgresql") < out.index("typescript")


def test_topics_for_plan_unknown_topic_ignored() -> None:
    out = topics_for_plan(technical_topics=["bogus-skill"])
    assert "bogus-skill" not in out


def test_topics_for_plan_behavioral_appended_last() -> None:
    out = topics_for_plan(technical_topics=[])
    assert out[-1] == "behavioral"


def test_topics_for_plan_dedupes_priorities() -> None:
    out = topics_for_plan(
        technical_topics=["postgresql", "PostgreSQL", "postgresql"]
    )
    assert out.count("postgresql") == 1


def test_generate_question_bank_returns_questions_for_every_difficulty() -> None:
    bank = generate_question_bank(technical_topics=[])
    by_difficulty: dict[str, int] = {}
    for q in bank:
        by_difficulty[q.difficulty] = by_difficulty.get(q.difficulty, 0) + 1
    for d in ALL_DIFFICULTIES:
        assert by_difficulty.get(d, 0) >= 3


def test_generate_question_bank_has_behavioral_category() -> None:
    bank = generate_question_bank(technical_topics=[])
    cats = {q.category for q in bank}
    assert CATEGORY_BEHAVIORAL in cats
    assert CATEGORY_TECHNICAL in cats
    assert CATEGORY_SYSTEM_DESIGN in cats


def test_generate_question_bank_minimum_size() -> None:
    bank = generate_question_bank(technical_topics=[])
    # 5 topics x 3 difficulties = 15
    assert len(bank) == 15


def test_generate_question_bank_prompts_are_non_empty() -> None:
    for q in generate_question_bank(technical_topics=[]):
        assert q.prompt.strip()
        assert q.topic.strip()


def test_generate_question_bank_outline_is_optional_but_present_in_bank() -> None:
    # The deterministic bank ships outlines for every entry.
    for q in generate_question_bank(technical_topics=[]):
        assert q.answer_outline is not None


def test_generate_question_bank_difficulty_values_are_valid() -> None:
    for q in generate_question_bank(technical_topics=[]):
        assert q.difficulty in ALL_DIFFICULTIES


def test_generate_question_bank_node_questions_present() -> None:
    bank = generate_question_bank(technical_topics=["node.js"])
    node_topics = [q for q in bank if q.topic == "node.js"]
    assert len(node_topics) == 3


def test_generate_question_bank_postgres_questions_present() -> None:
    bank = generate_question_bank(technical_topics=[])
    postgres_topics = [q for q in bank if q.topic == "postgresql"]
    difficulties = {q.difficulty for q in postgres_topics}
    assert difficulties == set(ALL_DIFFICULTIES)


def test_generate_question_bank_typescript_questions_present() -> None:
    bank = generate_question_bank(technical_topics=[])
    ts_topics = [q for q in bank if q.topic == "typescript"]
    assert len(ts_topics) == 3


def test_generate_question_bank_system_design_present() -> None:
    bank = generate_question_bank(technical_topics=[])
    sd = [q for q in bank if q.category == CATEGORY_SYSTEM_DESIGN]
    assert len(sd) == 3


def test_generate_question_bank_plan_id_is_zero_in_bank() -> None:
    for q in generate_question_bank(technical_topics=[]):
        assert q.plan_id == 0


def test_difficulty_constants_match_strings() -> None:
    assert DIFFICULTY_EASY == "easy"
    assert DIFFICULTY_MEDIUM == "medium"
    assert DIFFICULTY_HARD == "hard"


def test_generate_question_bank_topic_ordering_reflects_priority() -> None:
    bank = generate_question_bank(technical_topics=["postgresql"])
    # The postgresql questions should appear before typescript questions
    pg_index = next(i for i, q in enumerate(bank) if q.topic == "postgresql")
    ts_index = next(i for i, q in enumerate(bank) if q.topic == "typescript")
    assert pg_index < ts_index
