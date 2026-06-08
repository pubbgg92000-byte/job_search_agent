"""GET /telegram/status — bot connectivity + last delivery info.

POST /telegram/test-digest — manually trigger the daily digest delivery.
"""
from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from jobforge.config import get_settings
from jobforge.scheduler.runner import DEFAULT_RUN_AT, deliver_daily_digest
from jobforge.telegram.digest import build_digest_data

router = APIRouter()


def _next_run_at(run_at: time) -> str:
    now = datetime.now(UTC).astimezone()
    today_target = now.replace(
        hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0
    )
    if today_target <= now:
        today_target = today_target + timedelta(days=1)
    return today_target.isoformat()


@router.get("/status")
async def status() -> dict[str, Any]:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    configured = bool(token and chat_id)
    data = await build_digest_data(settings.sole_user_id)
    return {
        "configured": configured,
        "chat_id": chat_id,
        "bot_token_present": bool(token),
        "last_digest": {
            "generated_at": data.generated_at.isoformat()
            if data.generated_at
            else None,
            "top_matches": len(data.top_matches),
            "jobs_discovered_24h": data.jobs_discovered_24h,
            "applications_total": data.applications_total,
        },
        "next_scheduled_at": _next_run_at(DEFAULT_RUN_AT),
        "scheduled_run_at_local": DEFAULT_RUN_AT.isoformat(),
    }


@router.post("/test-digest")
async def send_test_digest() -> dict[str, Any]:
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        raise HTTPException(
            status_code=400,
            detail="Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
        )
    sent = await deliver_daily_digest()
    return {"sent": sent}
