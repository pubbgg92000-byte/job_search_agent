"""Pure builder tests for the interview study planner (no DB)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jobforge.applications import ApplicationError
from jobforge.interview.study_planner import (
    SUPPORTED_HORIZONS,
    StudyBlock,
    _build_blocks,
    pick_horizon_for_interview,
)


def test_supported_horizons_match_prd() -> None:
    assert SUPPORTED_HORIZONS == (1, 3, 7, 14)


def test_build_blocks_one_day_has_morning_through_evening() -> None:
    blocks = _build_blocks(
        horizon_days=1, topics=["TypeScript"], company="TestCo"
    )
    labels = [b.day_label for b in blocks]
    assert "Morning" in labels
    assert "Evening" in labels


def test_build_blocks_three_day_has_six_blocks() -> None:
    blocks = _build_blocks(
        horizon_days=3, topics=["Rust"], company=None
    )
    assert len(blocks) == 6


def test_build_blocks_seven_day_has_eight_blocks() -> None:
    blocks = _build_blocks(
        horizon_days=7, topics=["Rust", "Go"], company=None
    )
    assert len(blocks) == 8


def test_build_blocks_fourteen_day_has_fourteen_blocks() -> None:
    blocks = _build_blocks(
        horizon_days=14, topics=["Rust"], company=None
    )
    assert len(blocks) == 14


def test_build_blocks_rejects_unsupported_horizon() -> None:
    with pytest.raises(ApplicationError):
        _build_blocks(horizon_days=5, topics=["X"], company=None)


def test_build_blocks_includes_mock_interview_in_three_day() -> None:
    blocks = _build_blocks(
        horizon_days=3, topics=["TypeScript"], company=None
    )
    assert any(b.focus == "Mock interview" for b in blocks)


def test_build_blocks_includes_mock_in_seven_day() -> None:
    blocks = _build_blocks(
        horizon_days=7, topics=["TypeScript"], company=None
    )
    assert any(b.focus == "Mock interview" for b in blocks)


def test_build_blocks_fourteen_day_has_two_mock_interviews() -> None:
    blocks = _build_blocks(
        horizon_days=14, topics=["TypeScript"], company=None
    )
    mocks = [b for b in blocks if b.focus == "Mock interview"]
    assert len(mocks) == 2


def test_build_blocks_topic_appears_in_block_focus_or_activities() -> None:
    blocks = _build_blocks(
        horizon_days=3, topics=["GraphQL"], company=None
    )
    parts: list[str] = []
    for b in blocks:
        parts.append(b.focus)
        parts.extend(b.activities)
    blob = " ".join(parts).lower()
    assert "graphql" in blob


def test_build_blocks_company_name_appears_when_provided() -> None:
    blocks = _build_blocks(
        horizon_days=3, topics=["Rust"], company="Anthropic"
    )
    joined = " ".join(b.focus for b in blocks)
    assert "Anthropic" in joined


def test_build_blocks_default_topic_when_empty() -> None:
    blocks = _build_blocks(horizon_days=1, topics=[], company=None)
    # First technical block falls back to "Core role topics"
    assert any("Core role topics" in b.focus for b in blocks)


def test_build_blocks_one_day_total_minutes_reasonable() -> None:
    blocks = _build_blocks(horizon_days=1, topics=["Rust"], company=None)
    total = sum(b.duration_minutes for b in blocks)
    assert 120 <= total <= 240


def test_build_blocks_each_block_has_activities() -> None:
    for h in SUPPORTED_HORIZONS:
        blocks = _build_blocks(
            horizon_days=h, topics=["Rust"], company=None
        )
        for b in blocks:
            assert isinstance(b, StudyBlock)
            assert len(b.activities) >= 1


def test_build_blocks_no_block_has_zero_duration() -> None:
    for h in SUPPORTED_HORIZONS:
        blocks = _build_blocks(
            horizon_days=h, topics=["Rust"], company=None
        )
        for b in blocks:
            assert b.duration_minutes > 0


# ---------------- pick_horizon_for_interview ----------------


def test_pick_horizon_for_interview_none_defaults_to_seven() -> None:
    out = pick_horizon_for_interview(
        now=datetime(2026, 6, 8, tzinfo=UTC), interview_at=None
    )
    assert out == 7


def test_pick_horizon_for_interview_two_weeks_returns_fourteen() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    interview = now + timedelta(days=14)
    assert pick_horizon_for_interview(now=now, interview_at=interview) == 14


def test_pick_horizon_for_interview_ten_days_returns_seven() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    interview = now + timedelta(days=10)
    assert pick_horizon_for_interview(now=now, interview_at=interview) == 7


def test_pick_horizon_for_interview_five_days_returns_three() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    interview = now + timedelta(days=5)
    assert pick_horizon_for_interview(now=now, interview_at=interview) == 3


def test_pick_horizon_for_interview_two_days_returns_one() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    interview = now + timedelta(days=2)
    assert pick_horizon_for_interview(now=now, interview_at=interview) == 1


def test_pick_horizon_for_interview_past_interview_returns_one() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    interview = now - timedelta(days=1)
    assert pick_horizon_for_interview(now=now, interview_at=interview) == 1


def test_pick_horizon_for_interview_exact_day_boundaries() -> None:
    now = datetime(2026, 6, 8, tzinfo=UTC)
    assert pick_horizon_for_interview(
        now=now, interview_at=now + timedelta(days=7)
    ) == 7
    assert pick_horizon_for_interview(
        now=now, interview_at=now + timedelta(days=3)
    ) == 3
