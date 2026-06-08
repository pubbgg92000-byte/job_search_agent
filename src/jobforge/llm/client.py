from __future__ import annotations

import time
from typing import Any

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobforge.config import get_settings
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.llm")

_client: AsyncAnthropic | None = None

# Concurrency cap: never have more than N LLM calls in flight per process.
# Phase 1 is single-user; 4 covers the worst-case (parse, analyze, tailor x2 retry, cover_letter
# would still run sequentially in tailor_for_jd, so 4 is generous headroom for parallel callers).
_MAX_CONCURRENT_LLM_CALLS = 4
_semaphore: Any = None  # asyncio.Semaphore — lazily constructed in the active loop.


def _get_semaphore() -> Any:
    """Lazily create the semaphore in the current event loop.

    We avoid constructing it at import time so that pytest-asyncio's per-test
    event loops don't end up sharing a semaphore bound to a closed loop.
    """
    import asyncio

    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM_CALLS)
    return _semaphore

# Only retry on transient errors. Auth, bad-request, 422, 404 are caller bugs —
# retrying them just burns time and money.
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
)
async def call_structured(
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Force the model to emit a tool_use block matching `input_schema` and
    return the parsed input dict. The system prompt is marked cacheable.
    """
    settings = get_settings()
    chosen_model = model or settings.model_default

    async with _get_semaphore():
        log.info("llm.call.start", extra={"mode": "structured", "model": chosen_model, "tool": tool_name})
        t0 = time.perf_counter()
        try:
            response = await _get_client().messages.create(
                model=chosen_model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[
                    {
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": input_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            log.warning(
                "llm.call.error",
                extra={
                    "mode": "structured",
                    "model": chosen_model,
                    "tool": tool_name,
                    "error": type(exc).__name__,
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
            raise

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        usage = getattr(response, "usage", None)
        log.info(
            "llm.call.done",
            extra={
                "mode": "structured",
                "model": chosen_model,
                "tool": tool_name,
                "elapsed_ms": elapsed_ms,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return dict(block.input)  # type: ignore[arg-type]

    raise RuntimeError(f"Model did not emit expected tool_use block '{tool_name}'")


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
)
async def call_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Plain text response, system prompt cached."""
    settings = get_settings()
    chosen_model = model or settings.model_default

    async with _get_semaphore():
        log.info("llm.call.start", extra={"mode": "text", "model": chosen_model})
        t0 = time.perf_counter()
        try:
            response = await _get_client().messages.create(
                model=chosen_model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            log.warning(
                "llm.call.error",
                extra={
                    "mode": "text",
                    "model": chosen_model,
                    "error": type(exc).__name__,
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
            raise

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        usage = getattr(response, "usage", None)
        log.info(
            "llm.call.done",
            extra={
                "mode": "text",
                "model": chosen_model,
                "elapsed_ms": elapsed_ms,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        )

    parts: list[str] = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts).strip()
