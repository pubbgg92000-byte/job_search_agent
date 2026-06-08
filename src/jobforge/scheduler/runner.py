"""Composes scheduler + digest + notifier to deliver the daily 08:00 digest."""
from __future__ import annotations

from datetime import time

from jobforge.analytics import (
    build_recommendations,
    compute_funnel,
    record_daily_snapshot,
)
from jobforge.config import get_settings
from jobforge.logging_setup import get_logger
from jobforge.scheduler import Scheduler
from jobforge.telegram.digest import build_digest_data, render_digest_markdown
from jobforge.telegram.notifier import _escape_markdown_v2, _send_message_raw

log = get_logger("jobforge.scheduler.runner")

DEFAULT_RUN_AT = time(hour=8, minute=0)
ANALYTICS_RUN_AT = time(hour=8, minute=30)


def render_analytics_summary_markdown(
    funnel_stages_dict: dict[str, int],
    conversions_dict: dict[str, float],
    recs: list[dict[str, str]],
) -> str:
    """Render the analytics summary block. Pulled out so tests can exercise
    it without spinning up the scheduler."""
    s = funnel_stages_dict
    c = conversions_dict
    lines = [
        "*JobForge daily analytics*",
        "",
        f"Applications: {s['applications_created']} (submitted: {s['applications_submitted']})",
        f"Interviews: {s['interviews_scheduled']} scheduled · {s['interviews_completed']} completed",
        f"Offers: {s['offers_received']} received · {s['offers_accepted']} accepted",
        "",
        "*Conversion*",
        f"- Apply → reply: {round(c['apply_to_reply'] * 100)}%",
        f"- Apply → interview: {round(c['apply_to_interview'] * 100)}%",
        f"- Interview → offer: {round(c['interview_to_offer'] * 100)}%",
    ]
    if recs:
        lines.append("")
        lines.append("*Recommendations*")
        for r in recs[:3]:
            lines.append(f"- {r['title']}")
    return "\n".join(lines)


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


async def deliver_daily_analytics_summary() -> bool:
    """Record a snapshot and POST the analytics summary to Telegram."""
    settings = get_settings()
    user_id = settings.sole_user_id
    await record_daily_snapshot(user_id)
    funnel = await compute_funnel(user_id)
    recs = await build_recommendations(user_id)
    body = render_analytics_summary_markdown(
        funnel_stages_dict={
            "applications_created": funnel.stages.applications_created,
            "applications_submitted": funnel.stages.applications_submitted,
            "interviews_scheduled": funnel.stages.interviews_scheduled,
            "interviews_completed": funnel.stages.interviews_completed,
            "offers_received": funnel.stages.offers_received,
            "offers_accepted": funnel.stages.offers_accepted,
        },
        conversions_dict={
            "apply_to_reply": funnel.conversions.apply_to_reply,
            "apply_to_interview": funnel.conversions.apply_to_interview,
            "interview_to_offer": funnel.conversions.interview_to_offer,
        },
        recs=[{"title": r.title} for r in recs.items],
    )
    escaped = _escape_markdown_v2(body)
    log.info(
        "analytics.summary.delivery.start",
        extra={"user_id": user_id, "rec_count": len(recs.items)},
    )
    sent = await _send_message_raw(escaped, parse_mode="MarkdownV2")
    log.info("analytics.summary.delivery.done", extra={"sent": sent})
    return sent


def build_default_scheduler() -> Scheduler:
    """Scheduler with the daily digest + analytics-summary jobs pre-wired."""
    s = Scheduler()
    s.add_daily(name="daily_digest", run_at=DEFAULT_RUN_AT, fn=deliver_daily_digest)
    s.add_daily(
        name="daily_analytics_summary",
        run_at=ANALYTICS_RUN_AT,
        fn=deliver_daily_analytics_summary,
    )
    return s
