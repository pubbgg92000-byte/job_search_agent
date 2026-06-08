"""Optional LLM polish for outreach messages.

The deterministic templates are the canonical output. Polish rewrites the
body for tone and concision but is FORBIDDEN from introducing new facts:
the prompt instructs the model to only paraphrase the supplied draft. We
re-verify the output length cap after polish.

Tests always mock `call_text` — no network use.
"""
from __future__ import annotations

from jobforge.llm.client import call_text
from jobforge.logging_setup import get_logger
from jobforge.outreach.messages import (
    MAX_BODY_WORDS,
    DraftedMessage,
    _truncate_words,
    _word_count,
)

log = get_logger("jobforge.outreach.llm_polish")

_SYSTEM = (
    "You are an outreach editor. Rewrite the user's draft to be slightly "
    "warmer and more concise. Hard rules: do NOT invent facts about the "
    "candidate, the company, or the role; do NOT add claims of experience "
    "or skills; keep proper nouns exactly as written; keep the message "
    "under 180 words; preserve the greeting and sign-off shape. Output the "
    "rewritten body only — no preamble, no commentary."
)


async def polish_message(drafted: DraftedMessage) -> DraftedMessage:
    try:
        rewritten = await call_text(system=_SYSTEM, user=drafted.body)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning(
            "outreach.polish.error",
            extra={"kind": drafted.kind, "error": type(exc).__name__},
        )
        return drafted
    rewritten = (rewritten or "").strip()
    if not rewritten:
        return drafted
    if _word_count(rewritten) > MAX_BODY_WORDS:
        rewritten = _truncate_words(rewritten, limit=MAX_BODY_WORDS)
    return DraftedMessage(
        kind=drafted.kind,
        subject=drafted.subject,
        body=rewritten,
        channel=drafted.channel,
        template_version=drafted.template_version + "+polished",
        fields_used=dict(drafted.fields_used),
    )
