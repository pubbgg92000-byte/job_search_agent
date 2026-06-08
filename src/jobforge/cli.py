from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from jobforge.agents.resume_parser import parse_resume_pdf
from jobforge.config import get_settings
from jobforge.db.models import Profile, User
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger, new_request_id, setup_logging
from jobforge.pipelines.tailor_for_jd import tailor_for_jd
from jobforge.telegram.notifier import maybe_send_digest

setup_logging()
log = get_logger("jobforge.cli")

app = typer.Typer(help="JobForge — AI resume tailoring agent")
console = Console()


async def _ensure_user() -> int:
    """Idempotently ensure the SOLE_USER row exists. Returns its id."""
    settings = get_settings()
    async with session_scope() as session:
        result = await session.execute(select(User).where(User.id == settings.sole_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=settings.sole_user_id,
                name=settings.sole_user_name,
                email=settings.sole_user_email,
                telegram_chat_id=settings.telegram_chat_id,
            )
            session.add(user)
            await session.flush()
        return user.id


async def _ingest_resume(pdf_path: Path) -> int:
    """Parse a resume PDF and persist a Profile row. Returns its id."""
    user_id = await _ensure_user()
    raw_text, parsed = await parse_resume_pdf(pdf_path)
    async with session_scope() as session:
        profile = Profile(
            user_id=user_id,
            source_filename=str(pdf_path),
            raw_resume_text=raw_text,
            parsed_json=parsed,
        )
        session.add(profile)
        await session.flush()
        return profile.id


def _write_artifacts(*, tailored_md: str, cover_md: str, report: dict) -> Path:
    settings = get_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = settings.artifacts_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tailored.md").write_text(tailored_md, encoding="utf-8")
    (out_dir / "cover.md").write_text(cover_md, encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_dir


@app.command()
def ingest(
    resume: Path = typer.Option(..., "--resume", exists=True, dir_okay=False, readable=True),
) -> None:
    """Parse a resume PDF and store the structured profile. Prints the profile_id."""
    new_request_id()
    log.info("cli.ingest.start", extra={"resume_path": str(resume)})
    profile_id = asyncio.run(_ingest_resume(resume))
    log.info("cli.ingest.done", extra={"profile_id": profile_id})
    console.print(f"[green]Profile ingested:[/green] profile_id=[bold]{profile_id}[/bold]")


@app.command()
def tailor(
    resume: Path = typer.Option(..., "--resume", exists=True, dir_okay=False, readable=True),
    jd: Path = typer.Option(..., "--jd", exists=True, dir_okay=False, readable=True),
    company: str | None = typer.Option(None, "--company", help="Override company name"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Send Telegram digest if configured"),
) -> None:
    """Run the full pipeline: parse resume, analyze JD, tailor, score, cover letter, persist, notify."""
    new_request_id()
    log.info(
        "cli.tailor.start",
        extra={"resume_path": str(resume), "jd_path": str(jd), "company": company},
    )

    async def _run() -> None:
        profile_id = await _ingest_resume(resume)
        jd_text = jd.read_text(encoding="utf-8")
        result = await tailor_for_jd(
            profile_id=profile_id,
            jd_text=jd_text,
            company_name=company,
        )

        report = {
            "artifact_id": result.artifact_id,
            "profile_id": result.profile_id,
            "job_id": result.job_id,
            "company": result.company,
            "title": result.title,
            "score_before": result.score_before,
            "score_after": result.score_after,
            "missing_keywords": result.missing_keywords,
        }
        out_dir = _write_artifacts(
            tailored_md=result.tailored_resume_md,
            cover_md=result.cover_letter_md,
            report=report,
        )

        table = Table(title="Tailoring report")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Company", str(result.company))
        table.add_row("Title", str(result.title))
        table.add_row("Score (before tailoring)", f"{result.score_before}/100")
        table.add_row("Score (after tailoring)", f"{result.score_after}/100")
        table.add_row("Missing keywords", ", ".join(result.missing_keywords) or "(none)")
        table.add_row("Artifacts dir", str(out_dir))
        console.print(table)

        if notify:
            await maybe_send_digest(result, out_dir)

    asyncio.run(_run())


@app.command()
def scheduler(
    interval: int = typer.Option(60, "--interval", help="Tick interval in seconds"),
) -> None:
    """Run the in-process daily-digest scheduler. Blocks forever."""
    from jobforge.scheduler.runner import build_default_scheduler

    new_request_id()
    log.info("cli.scheduler.start", extra={"interval": interval})
    s = build_default_scheduler()
    try:
        asyncio.run(s.run_forever(interval_seconds=interval))
    except KeyboardInterrupt:
        log.info("cli.scheduler.stop")


@app.command(name="telegram-bot")
def telegram_bot() -> None:
    """Run the Telegram long-polling bot. Blocks forever."""
    from jobforge.telegram.bot import build_default_bot, run_polling

    new_request_id()
    log.info("cli.telegram_bot.start")
    try:
        asyncio.run(run_polling(build_default_bot()))
    except KeyboardInterrupt:
        log.info("cli.telegram_bot.stop")


@app.command()
def digest(
    send: bool = typer.Option(False, "--send", help="Actually deliver to Telegram"),
) -> None:
    """Build the daily digest. With --send, posts it to the configured chat."""
    from jobforge.telegram.digest import build_digest_data, render_digest_markdown
    from jobforge.telegram.notifier import _escape_markdown_v2, _send_message_raw

    settings = get_settings()
    new_request_id()
    log.info("cli.digest.start", extra={"send": send})

    async def _run() -> None:
        data = await build_digest_data(settings.sole_user_id)
        body = render_digest_markdown(data)
        console.print(body)
        if send:
            ok = await _send_message_raw(_escape_markdown_v2(body), parse_mode="MarkdownV2")
            console.print(f"[green]sent={ok}[/green]")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
