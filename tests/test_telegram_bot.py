"""Telegram bot dispatch + digest content tests.

We don't run the long-polling loop. Instead, we exercise the command-handler
dispatcher and the digest-builder/renderer in isolation.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobforge.telegram.bot import TelegramBot, build_default_bot
from jobforge.telegram.digest import DigestData, render_digest_markdown

# --------------------------- digest rendering -----------------------------
# Plain synchronous tests — no asyncio mark.


def test_render_digest_includes_jobs_count_and_no_matches_message() -> None:
    data = DigestData(
        user_id=1,
        generated_at=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
        jobs_discovered_24h=12,
    )
    md = render_digest_markdown(data)
    assert "Jobs discovered (24h): 12" in md
    assert "No matches today." in md


def test_render_digest_lists_top_matches() -> None:
    data = DigestData(
        user_id=1,
        generated_at=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
        jobs_discovered_24h=5,
        top_matches=[
            {"id": 1, "title": "Backend Eng", "company": "Acme", "url": "u", "score": 87},
            {"id": 2, "title": "Frontend Eng", "company": "Globex", "url": "u", "score": 81},
        ],
    )
    md = render_digest_markdown(data)
    assert "Backend Eng @ Acme" in md
    assert "87/100" in md


def test_render_digest_lists_skill_gaps() -> None:
    data = DigestData(
        user_id=1,
        generated_at=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
        jobs_discovered_24h=0,
        skill_gaps=[
            {"skill": "Rust", "importance_score": 88},
            {"skill": "Docker", "importance_score": 71},
        ],
    )
    md = render_digest_markdown(data)
    assert "Rust (importance 88)" in md


def test_render_digest_includes_application_totals() -> None:
    data = DigestData(
        user_id=1,
        generated_at=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
        jobs_discovered_24h=0,
        applications_total=12,
        interviews=3,
        offers=1,
        rejections=4,
    )
    md = render_digest_markdown(data)
    assert "Applications: 12 total" in md
    assert "3 interview-stage" in md
    assert "1 offers" in md
    assert "4 rejected" in md


# --------------------------- bot dispatch ---------------------------------


@pytest.mark.asyncio
async def test_dispatch_returns_none_on_non_command() -> None:
    bot = TelegramBot(handlers={})
    assert await bot.dispatch("hello there") is None


@pytest.mark.asyncio
async def test_dispatch_unknown_command_returns_message() -> None:
    bot = TelegramBot(handlers={})
    reply = await bot.dispatch("/wat")
    assert "Unknown command" in reply


@pytest.mark.asyncio
async def test_dispatch_strips_botname_suffix() -> None:
    calls: list[str] = []

    async def handler(args: list[str]) -> str:
        calls.append(",".join(args))
        return "ok"

    bot = TelegramBot(handlers={"jobs": handler})
    assert await bot.dispatch("/jobs@MyBot 5") == "ok"
    assert calls == ["5"]


@pytest.mark.asyncio
async def test_dispatch_handler_exception_returns_friendly_message() -> None:
    async def handler(args: list[str]) -> str:
        raise RuntimeError("boom")

    bot = TelegramBot(handlers={"err": handler})
    reply = await bot.dispatch("/err")
    assert "something went wrong" in reply.lower()


@pytest.mark.asyncio
async def test_default_bot_has_all_prd_commands() -> None:
    bot = build_default_bot()
    expected = {"jobs", "matches", "applications", "interviews", "stats", "gaps"}
    assert expected <= set(bot.handlers)


@pytest.mark.asyncio
async def test_dispatch_help_lists_commands() -> None:
    bot = build_default_bot()
    reply = await bot.dispatch("/help")
    for cmd in ("/jobs", "/matches", "/stats", "/gaps"):
        assert cmd in reply
