"""Composes scheduler + digest + notifier to deliver the daily 08:00 digest."""
from __future__ import annotations

from datetime import time

from jobforge.config import get_settings
from jobforge.logging_setup import get_logger
from jobforge.scheduler import Scheduler
from jobforge.telegram.digest import build_digest_data, render_digest_markdown
from jobforge.telegram.notifier import _escape_markdown_v2, _send_message_raw

log = get_logger("jobforge.scheduler.runner")

DEFAULT_RUN_AT = time(hour=8, minute=0)


async def deliver_daily_digest() -> bool:
    """Build today's digest for the sole user and POST it to Telegram. Returns True on send."""
    settings = get_settings()
    data = await build_digest_data(settings.sole_user_id)
    body = render_digest_markdown(data)
    escaped = _escape_markdown_v2(body)
    log.info(
        "digest.delivery.start",
        extra={
            "user_id": data.user_id,
            "top_matches": len(data.top_matches),
            "applications_total": data.applications_total,
        },
    )
    sent = await _send_message_raw(escaped, parse_mode="MarkdownV2")
    log.info("digest.delivery.done", extra={"sent": sent})
    return sent


def build_default_scheduler() -> Scheduler:
    """Scheduler with the daily digest job pre-wired."""
    s = Scheduler()
    s.add_daily(name="daily_digest", run_at=DEFAULT_RUN_AT, fn=deliver_daily_digest)
    return s
