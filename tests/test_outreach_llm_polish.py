"""LLM polish is mocked — verify it only paraphrases and respects caps."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from jobforge.outreach.llm_polish import polish_message
from jobforge.outreach.messages import (
    KIND_INITIAL,
    MessageContext,
    generate_message,
)


def _draft():
    return generate_message(
        KIND_INITIAL,
        MessageContext(
            company="Acme",
            contact_name="Sam",
            role_title="Engineer",
            matched_skills=["Python", "PostgreSQL"],
        ),
    )


async def test_polish_returns_rewritten_body() -> None:
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(return_value="Hi Sam,\n\nQuick warmer note about Acme."),
    ):
        polished = await polish_message(_draft())
    assert "warmer" in polished.body
    assert polished.template_version.endswith("+polished")


async def test_polish_truncates_overlong_response() -> None:
    long_text = ("hello " * 500).strip()
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(return_value=long_text),
    ):
        polished = await polish_message(_draft())
    assert len(polished.body.split()) <= 180


async def test_polish_falls_back_to_draft_on_empty_response() -> None:
    drafted = _draft()
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(return_value="   "),
    ):
        polished = await polish_message(drafted)
    assert polished.body == drafted.body


async def test_polish_returns_draft_on_llm_failure() -> None:
    drafted = _draft()
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        polished = await polish_message(drafted)
    assert polished.body == drafted.body
    assert polished.template_version == drafted.template_version


async def test_polish_preserves_subject_and_channel() -> None:
    drafted = _draft()
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(return_value="Hi Sam,\n\nRewritten."),
    ):
        polished = await polish_message(drafted)
    assert polished.subject == drafted.subject
    assert polished.channel == drafted.channel


async def test_polish_carries_through_fields_used() -> None:
    drafted = _draft()
    with patch(
        "jobforge.outreach.llm_polish.call_text",
        new=AsyncMock(return_value="Hi Sam,\n\nRewritten."),
    ):
        polished = await polish_message(drafted)
    assert polished.fields_used == drafted.fields_used


async def test_polish_invokes_llm_with_draft_body() -> None:
    drafted = _draft()
    mock = AsyncMock(return_value="Hi Sam,\n\nRewritten.")
    with patch("jobforge.outreach.llm_polish.call_text", new=mock):
        await polish_message(drafted)
    kwargs = mock.call_args.kwargs
    assert kwargs["user"] == drafted.body
    assert "do NOT invent facts" in kwargs["system"]
