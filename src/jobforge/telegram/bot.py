"""Telegram bot — command dispatcher.

Phase 2B scope: command-handler architecture + a long-poll runner. The
runner is started via the CLI (`jobforge telegram-bot start`) and isn't
required for the rest of the system to work.

Each command handler returns a string (Markdown text). The runner takes care
of escaping for MarkdownV2 and POSTing back to the chat.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import desc, select

from jobforge.applications import stats as application_stats
from jobforge.applications.status import (
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
)
from jobforge.config import get_settings
from jobforge.db.models import Application, DiscoveredJob, Profile
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger, new_request_id
from jobforge.match import match_job
from jobforge.preferences import apply_exclusions, load_preferences
from jobforge.skills import compute_gaps
from jobforge.telegram.notifier import _API, _escape_markdown_v2

log = get_logger("jobforge.telegram.bot")

CommandHandler = Callable[[list[str]], Awaitable[str]]


@dataclass
class TelegramBot:
    handlers: dict[str, CommandHandler]

    async def dispatch(self, text: str) -> str | None:
        """Parse `/command arg arg` and route to a handler. Returns reply text or None."""
        text = (text or "").strip()
        if not text.startswith("/"):
            return None
        # Strip the optional @botname suffix Telegram appends in group chats.
        head, *rest = text.split(maxsplit=1)
        cmd = head.split("@", 1)[0][1:].lower()
        args = rest[0].split() if rest else []
        handler = self.handlers.get(cmd)
        if handler is None:
            return f"Unknown command: /{cmd}"
        try:
            return await handler(args)
        except Exception as exc:
            log.warning(
                "bot.handler.error",
                extra={"cmd": cmd, "error": type(exc).__name__},
            )
            return "Sorry — something went wrong handling that command."


# ----------------- handlers -----------------


async def _latest_profile(user_id: int) -> Profile | None:
    async with session_scope() as session:
        return (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()


async def _cmd_jobs(args: list[str]) -> str:
    limit = _parse_int(args, default=5, lo=1, hi=20)
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(limit)
            )
        ).scalars().all()
    if not rows:
        return "No jobs discovered yet — try POST /jobs/sync first."
    lines = [f"Last {len(rows)} discovered jobs:"]
    for r in rows:
        lines.append(f"- {r.title} @ {r.company} ({r.source})")
    return "\n".join(lines)


async def _cmd_matches(args: list[str]) -> str:
    limit = _parse_int(args, default=5, lo=1, hi=20)
    settings = get_settings()
    profile = await _latest_profile(settings.sole_user_id)
    if profile is None:
        return "No profile yet — upload one via /profile."
    prefs_dto = await load_preferences(settings.sole_user_id)
    prefs = prefs_dto.to_match_preferences()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(200)
            )
        ).scalars().all()
    scored = []
    for r in rows:
        d = {
            "title": r.title,
            "company": r.company,
            "location": r.location,
            "remote": r.remote,
            "description": r.description,
            "posted_at": r.posted_at,
            "salary_min": r.salary_min,
            "salary_max": r.salary_max,
            "salary_currency": r.salary_currency,
        }
        if apply_exclusions(prefs_dto, d):
            continue
        m = match_job(profile=profile.parsed_json, job=d, prefs=prefs)
        scored.append((r, m))
    scored.sort(key=lambda pair: pair[1].score, reverse=True)
    if not scored:
        return "No matches yet."
    lines = ["Top matches:"]
    for row, m in scored[:limit]:
        lines.append(f"- {row.title} @ {row.company} — {m.score}/100")
    return "\n".join(lines)


async def _cmd_applications(args: list[str]) -> str:
    settings = get_settings()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Application)
                .where(Application.user_id == settings.sole_user_id)
                .order_by(desc(Application.created_at))
                .limit(10)
            )
        ).scalars().all()
    if not rows:
        return "No applications tracked yet."
    lines = [f"Last {len(rows)} applications:"]
    for r in rows:
        lines.append(f"- [{r.status}] {r.title} @ {r.company}")
    return "\n".join(lines)


async def _cmd_interviews(args: list[str]) -> str:
    settings = get_settings()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Application)
                .where(Application.user_id == settings.sole_user_id)
                .where(
                    Application.status.in_(
                        [STATUS_INTERVIEW_SCHEDULED, STATUS_INTERVIEW_COMPLETED]
                    )
                )
                .order_by(desc(Application.last_updated))
                .limit(10)
            )
        ).scalars().all()
    if not rows:
        return "No interviews on the board."
    lines = ["Interviews:"]
    for r in rows:
        lines.append(f"- [{r.status}] {r.title} @ {r.company}")
    return "\n".join(lines)


async def _cmd_stats(args: list[str]) -> str:
    settings = get_settings()
    s = await application_stats(settings.sole_user_id)
    return (
        f"Apps: {s.total} total | Interviews: {s.interviews} | "
        f"Offers: {s.offers} | Rejections: {s.rejections}\n"
        f"Interview rate: {int(s.interview_rate * 100)}% | "
        f"Offer rate: {int(s.offer_rate * 100)}% | "
        f"Acceptance rate: {int(s.acceptance_rate * 100)}%"
    )


async def _cmd_gaps(args: list[str]) -> str:
    settings = get_settings()
    profile = await _latest_profile(settings.sole_user_id)
    if profile is None:
        return "No profile yet — upload one via /profile."
    prefs_dto = await load_preferences(settings.sole_user_id)
    prefs = prefs_dto.to_match_preferences()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DiscoveredJob)
                .order_by(desc(DiscoveredJob.first_seen_at))
                .limit(200)
            )
        ).scalars().all()
    job_dicts = [
        {
            "title": r.title,
            "company": r.company,
            "location": r.location,
            "remote": r.remote,
            "description": r.description,
            "posted_at": r.posted_at,
            "salary_min": r.salary_min,
            "salary_max": r.salary_max,
            "salary_currency": r.salary_currency,
        }
        for r in rows
        if not apply_exclusions(
            prefs_dto,
            {"company": r.company, "title": r.title, "description": r.description},
        )
    ]
    report = compute_gaps(
        profile=profile.parsed_json, jobs=job_dicts, prefs=prefs, top_n=5
    )
    if not report.top_gaps:
        return "No skill gaps detected — your profile covers the catalogue well."
    lines = ["Top skill gaps:"]
    for g in report.top_gaps:
        lines.append(f"- {g.skill} (importance {g.importance_score})")
    return "\n".join(lines)


async def _cmd_help(args: list[str]) -> str:
    return (
        "Commands:\n"
        "/jobs [n] — latest discovered jobs\n"
        "/matches [n] — top matches against your profile\n"
        "/applications — recent applications\n"
        "/interviews — interview-stage apps\n"
        "/stats — application funnel\n"
        "/gaps — top missing skills\n"
        "/help — this message"
    )


def _parse_int(args: list[str], *, default: int, lo: int, hi: int) -> int:
    if not args:
        return default
    try:
        v = int(args[0])
    except ValueError:
        return default
    return max(lo, min(hi, v))


def build_default_bot() -> TelegramBot:
    return TelegramBot(
        handlers={
            "jobs": _cmd_jobs,
            "matches": _cmd_matches,
            "applications": _cmd_applications,
            "interviews": _cmd_interviews,
            "stats": _cmd_stats,
            "gaps": _cmd_gaps,
            "help": _cmd_help,
            "start": _cmd_help,
        }
    )


# ----------------- long-poll runner -----------------


async def _send_reply(
    chat_id: str | int, text: str, token: str
) -> None:
    url = f"{_API}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": _escape_markdown_v2(text),
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
        )


async def run_polling(
    bot: TelegramBot,
    *,
    poll_timeout: int = 30,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Long-poll the Telegram getUpdates endpoint and dispatch commands.

    Stops cleanly when `stop_event` is set. Used by the `jobforge telegram-bot`
    CLI command; not exercised in unit tests.
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        log.warning("bot.polling.skipped", extra={"reason": "no_token"})
        return
    offset = 0
    log.info("bot.polling.start")
    while not (stop_event and stop_event.is_set()):
        try:
            async with httpx.AsyncClient(timeout=poll_timeout + 5) as client:
                resp = await client.get(
                    f"{_API}/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": poll_timeout},
                )
                payload = resp.json()
        except Exception as exc:
            log.warning("bot.polling.error", extra={"error": type(exc).__name__})
            await asyncio.sleep(5)
            continue
        for update in payload.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message")
            if not message:
                continue
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text") or ""
            new_request_id()
            reply = await bot.dispatch(text)
            if reply is not None and chat_id is not None:
                await _send_reply(chat_id, reply, token)
    log.info("bot.polling.stop")
