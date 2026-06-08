from __future__ import annotations

from pathlib import Path

import httpx

from jobforge.config import get_settings
from jobforge.pipelines.tailor_for_jd import TailorResult

_API = "https://api.telegram.org"


def _escape_markdown_v2(text: str) -> str:
    """Telegram MarkdownV2 requires escaping these characters."""
    specials = r"_*[]()~`>#+-=|{}.!"
    return "".join("\\" + ch if ch in specials else ch for ch in text)


def _format_digest(result: TailorResult, out_dir: Path) -> str:
    company = result.company or "Unknown company"
    title = result.title or "Unknown role"
    missing = ", ".join(result.missing_keywords[:8]) if result.missing_keywords else "none"
    body = (
        f"*JobForge — tailored*\n\n"
        f"Role: {title} @ {company}\n"
        f"ATS score: {result.score_before} → {result.score_after}/100\n"
        f"Top missing: {missing}\n\n"
        f"Artifacts: `{out_dir}`"
    )
    return _escape_markdown_v2(body)


async def _send_message_raw(
    text: str, *, parse_mode: str = "MarkdownV2"
) -> bool:
    """Send raw text to the configured Telegram chat. Returns True if sent.

    Used by both the tailor digest and the scheduled daily digest. Returns
    False (without raising) when Telegram is not configured.
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    url = f"{_API}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()
    return True


async def maybe_send_digest(result: TailorResult, out_dir: Path) -> bool:
    """Send the tailor digest if Telegram is configured. Returns True if sent."""
    text = _format_digest(result, out_dir)
    return await _send_message_raw(text, parse_mode="MarkdownV2")
