"""PlaywrightApplicationAgent — the orchestrator.

Drives an `ApplicationPackage` through a real browser:

    open(job_url)
    for logical_field in FILLABLE_FIELDS_ORDER:
        if selector for (platform, logical_field) and value in package:
            fill or upload
            screenshot
    state = READY_FOR_REVIEW

Then waits for the API approval call to invoke `.submit()`, which clicks the
platform's submit button and screenshots the result. All transitions write to
`application_events` via the per-session helper in `apply_assist.py`.

The runner is browser-agnostic: it takes a `BrowserAgent` (the ABC). Unit
tests pass a FakeBrowser stub; integration tests pass `PlaywrightChromiumAgent`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from jobforge.agents_phase3.browser import BrowserAgent
from jobforge.application_agent.base import ApplicationPackage, ATSPlatform
from jobforge.application_agent.browser.selectors import (
    FILLABLE_FIELDS_ORDER,
    SelectorSpec,
    selectors_for,
)
from jobforge.application_agent.browser.session import (
    STATE_FAILED,
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    ApplyAssistSession,
)
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.apply_assist.runner")


class RunnerError(Exception):
    """Raised when the runner can't proceed (no submit selector, bad state, etc.)."""


class EventSink(Protocol):
    """The runner emits state-change events through this callback.

    The real implementation in `applications/apply_assist.py` writes to
    `application_events` and updates the `apply_sessions` row. Tests substitute
    a list-appending fake.
    """

    async def __call__(
        self,
        *,
        session: ApplyAssistSession,
        event_type: str,
        notes: str | None = None,
    ) -> None: ...


def _resolve_value_for_field(
    platform: ATSPlatform, logical: str, package: ApplicationPackage
) -> str | None:
    """Pull the package's value for `logical`, handling Lever's collapsed name.

    `mapper.map_profile` writes wire names into `applicant_fields`. For browser
    filling we want LOGICAL keys (`first_name`, `email`, ...), so we project
    back: for Greenhouse/Ashby the mapper already used logical-looking keys
    (`first_name`, `firstName`), for Lever it used `name`. We accept either.
    """
    fields = package.applicant_fields
    if logical == "name":
        if platform == ATSPlatform.LEVER:
            return fields.get("name")
        return None
    if logical in ("first_name", "last_name"):
        if platform == ATSPlatform.LEVER:
            return None  # Lever uses the combined 'name' field above
        if platform == ATSPlatform.ASHBY:
            wire = "firstName" if logical == "first_name" else "lastName"
            return fields.get(wire) or fields.get(logical)
        return fields.get(logical)
    if logical == "linkedin":
        for key, val in fields.items():
            if "linkedin" in key.lower():
                return val
        return None
    if logical == "cover_letter":
        return package.cover_letter_path
    if logical == "resume":
        return package.resume_path
    return fields.get(logical)


def _value_kind_matches(spec: SelectorSpec, value: str) -> bool:
    """Catch obvious config drift: a file selector with a non-file value, etc."""
    if spec.kind == "file":
        return value.endswith((".pdf", ".md", ".txt", ".doc", ".docx"))
    return True


class PlaywrightApplicationAgent:
    """High-level orchestrator over any `BrowserAgent`.

    Holds no state itself — all state lives on the passed `ApplyAssistSession`.
    The same instance can be reused across sessions but most callers will
    construct one per session for clarity.
    """

    def __init__(
        self,
        browser: BrowserAgent,
        *,
        emit: EventSink,
        screenshot_dir: Path,
    ) -> None:
        self.browser = browser
        self.emit = emit
        self.screenshot_dir = screenshot_dir

    async def _shot(self, session: ApplyAssistSession, label: str) -> str:
        out_dir = self.screenshot_dir / f"session-{session.id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        idx = len(session.screenshot_paths)
        path = out_dir / f"{idx:02d}-{label}.png"
        await self.browser.screenshot(str(path))
        session.screenshot_paths.append(str(path))
        session.touch()
        return str(path)

    async def fill_form(
        self,
        session: ApplyAssistSession,
        package: ApplicationPackage,
    ) -> None:
        """Open + fill + screenshot. Transitions session to READY_FOR_REVIEW.

        On any failure, transitions session to FAILED, closes the browser, and
        re-raises a RunnerError with the underlying message. The session lock
        is the caller's responsibility (acquired in apply_assist.start_session).
        """
        if session.platform == ATSPlatform.UNKNOWN:
            await self._fail(session, "unknown ATS platform; refusing to drive form")
            raise RunnerError("unknown ATS platform")

        await self.emit(session=session, event_type="apply_assist.form_started")
        try:
            await self.browser.open(session.job_url)
            await self._shot(session, "opened")

            specs = selectors_for(session.platform)
            skipped: list[str] = []
            filled: list[str] = []
            for logical in FILLABLE_FIELDS_ORDER:
                spec = specs.get(logical)
                if spec is None:
                    continue
                value = _resolve_value_for_field(session.platform, logical, package)
                if value is None or value == "":
                    skipped.append(logical)
                    continue
                if not _value_kind_matches(spec, value):
                    skipped.append(f"{logical}:bad-kind")
                    continue
                await self._try_each(spec, value)
                filled.append(logical)
                await self._shot(session, f"filled-{logical}")

            session.extra["filled_fields"] = filled
            session.extra["skipped_fields"] = skipped
            await self._shot(session, "form-complete")
            await self.emit(
                session=session,
                event_type="apply_assist.form_completed",
                notes=f"filled={','.join(filled) or '(none)'} skipped={','.join(skipped) or '(none)'}",
            )

            from datetime import UTC, datetime

            session.state = STATE_READY_FOR_REVIEW
            session.ready_for_review_at = datetime.now(UTC)
            session.touch()
            await self.emit(session=session, event_type="apply_assist.ready_for_review")
        except RunnerError:
            raise
        except Exception as exc:
            await self._fail(session, f"{type(exc).__name__}: {exc}")
            raise RunnerError(str(exc)) from exc

    async def submit(self, session: ApplyAssistSession) -> None:
        """Click the platform's submit button. Pre: state == READY_FOR_REVIEW."""
        if session.state != STATE_READY_FOR_REVIEW:
            raise RunnerError(
                f"cannot submit from state '{session.state}'; expected ready_for_review"
            )
        spec = selectors_for(session.platform).get("submit")
        if spec is None:
            await self._fail(session, "no submit selector for platform")
            raise RunnerError("no submit selector for platform")
        try:
            await self.browser.click(spec.primary)
            await self._shot(session, "submitted")
            from datetime import UTC, datetime

            session.state = STATE_SUBMITTED
            session.completed_at = datetime.now(UTC)
            session.touch()
            await self.emit(session=session, event_type="apply_assist.submitted")
        except Exception as exc:
            await self._fail(session, f"submit failed: {type(exc).__name__}: {exc}")
            raise RunnerError(str(exc)) from exc
        finally:
            await self._close_quietly(session)

    async def cancel(self, session: ApplyAssistSession, *, reason: str = "user-cancelled") -> None:
        from datetime import UTC, datetime

        from jobforge.application_agent.browser.session import STATE_CANCELLED

        session.state = STATE_CANCELLED
        session.completed_at = datetime.now(UTC)
        session.error_message = reason
        session.touch()
        await self.emit(session=session, event_type="apply_assist.cancelled", notes=reason)
        await self._close_quietly(session)

    # ---- internals -----------------------------------------------------

    async def _try_each(self, spec: SelectorSpec, value: str) -> None:
        """Try the primary selector then each fallback. Bubble the last error."""
        last: Exception | None = None
        for candidate in spec.candidates():
            try:
                if spec.kind == "file":
                    await self.browser.upload(candidate, value)
                else:
                    await self.browser.fill(candidate, value)
                return
            except Exception as exc:
                last = exc
        if last is not None:
            raise last

    async def _fail(self, session: ApplyAssistSession, message: str) -> None:
        from datetime import UTC, datetime

        session.state = STATE_FAILED
        session.error_message = message
        session.completed_at = datetime.now(UTC)
        session.touch()
        await self.emit(session=session, event_type="apply_assist.failed", notes=message)
        await self._close_quietly(session)

    async def _close_quietly(self, session: ApplyAssistSession) -> None:
        try:
            await self.browser.close()
        except Exception as exc:
            log.warning(
                "apply_assist.runner.close_failed",
                extra={"session_id": session.id, "error": str(exc)},
            )
        finally:
            session.browser = None
