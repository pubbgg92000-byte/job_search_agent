"""Apply-assist orchestration: glue between the registry, runner, and DB.

Public surface:
    start_session(application_id, *, resume_path=None, cover_letter_path=None, profile_id=None)
    get_session(session_id)
    list_events_for_session(application_id)
    approve(session_id)
    cancel(session_id)
    serialize_session(session)

Internally:
    - Builds an ApplicationPackage from the application + sole-user profile.
    - Creates a registry entry (capping concurrency).
    - Inserts an `apply_sessions` row that mirrors the in-memory state.
    - Spawns the runner against a real PlaywrightChromiumAgent (default) or a
      pluggable factory for tests.
    - Every state change (form_started → form_completed → ready_for_review →
      submitted/failed/cancelled) writes an `application_events` row and
      refreshes the `apply_sessions` row.
    - On successful submit, calls `applications.update_status(to_status="applied")`
      so the funnel + status_change event happen exactly the same way they would
      have via a manual PATCH.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from jobforge.agents_phase3.browser import BrowserAgent
from jobforge.agents_phase3.playwright_browser import PlaywrightChromiumAgent
from jobforge.application_agent import prepare_package
from jobforge.application_agent.browser import (
    PlaywrightApplicationAgent,
    RegistryError,
    RunnerError,
    get_registry,
)
from jobforge.application_agent.browser.session import (
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    ApplyAssistSession,
)
from jobforge.applications import (
    ApplicationError,
    StatusUpdateRequest,
    update_status,
)
from jobforge.applications.status import STATUS_APPLIED
from jobforge.config import get_settings
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    ApplySession,
    DiscoveredJob,
    Profile,
)
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.apply_assist")


class ApplyAssistError(Exception):
    """Service-level error (missing application, registry full, illegal transition)."""


BrowserFactory = Callable[[bool], BrowserAgent]


def _default_browser_factory(headless: bool) -> BrowserAgent:
    return PlaywrightChromiumAgent(
        headless=headless,
        step_timeout_ms=get_settings().apply_assist_step_timeout_ms,
    )


_browser_factory: BrowserFactory = _default_browser_factory


def set_browser_factory(factory: BrowserFactory | None) -> None:
    """Tests override the factory to inject a FakeBrowser without real Chromium."""
    global _browser_factory
    _browser_factory = factory or _default_browser_factory


# ----------------------------------------------------------------------
# DB helpers
# ----------------------------------------------------------------------


async def _record_event(
    application_id: int, event_type: str, *, notes: str | None = None
) -> None:
    async with session_scope() as ss:
        ss.add(
            ApplicationEvent(
                application_id=application_id,
                event_type=event_type,
                notes=notes,
                occurred_at=datetime.now(UTC),
            )
        )


async def _persist_session(s: ApplyAssistSession, *, insert: bool = False) -> None:
    """Insert or update the durable `apply_sessions` row from in-memory state."""
    async with session_scope() as ss:
        if insert:
            row = ApplySession(
                id=s.id,
                application_id=s.application_id,
                platform=s.platform.value,
                state=s.state,
                headless=s.headless,
                job_url=s.job_url,
                screenshot_paths=list(s.screenshot_paths),
                error_message=s.error_message,
                started_at=s.started_at,
                ready_for_review_at=s.ready_for_review_at,
                completed_at=s.completed_at,
                extra_json=dict(s.extra) or None,
            )
            ss.add(row)
            await ss.flush()
            return
        row = await ss.get(ApplySession, s.id)
        if row is None:
            return
        row.state = s.state
        row.screenshot_paths = list(s.screenshot_paths)
        row.error_message = s.error_message
        row.ready_for_review_at = s.ready_for_review_at
        row.completed_at = s.completed_at
        row.extra_json = dict(s.extra) or None


async def _next_session_id() -> int:
    """Pick the next id by checking max(apply_sessions.id) at insert time.

    Registry assigns its own incrementing id when uncoupled; we synchronize
    them here so the DB and in-memory id always match.
    """
    async with session_scope() as ss:
        row = (
            await ss.execute(select(ApplySession).order_by(ApplySession.id.desc()).limit(1))
        ).scalar_one_or_none()
        return (row.id + 1) if row is not None else 1


# ----------------------------------------------------------------------
# Event sink (consumed by the runner)
# ----------------------------------------------------------------------


async def _emit(*, session: ApplyAssistSession, event_type: str, notes: str | None = None) -> None:
    log.info(
        "apply_assist.event",
        extra={"session_id": session.id, "application_id": session.application_id, "type": event_type},
    )
    await _record_event(session.application_id, event_type, notes=notes)
    await _persist_session(session)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


async def start_session(
    application_id: int,
    *,
    profile_id: int | None = None,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
) -> ApplyAssistSession:
    settings = get_settings()
    async with session_scope() as ss:
        app_row = await ss.get(Application, application_id)
        if app_row is None or app_row.user_id != settings.sole_user_id:
            raise ApplyAssistError(f"application {application_id} not found")
        if not app_row.url:
            raise ApplyAssistError("application has no job url; cannot drive a browser")
        job_url = app_row.url

        if profile_id is None:
            prof = (
                await ss.execute(
                    select(Profile)
                    .where(Profile.user_id == settings.sole_user_id)
                    .order_by(Profile.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if prof is None:
                raise ApplyAssistError("no profile uploaded yet; ingest a resume first")
            profile_id = prof.id

        discovered_job_id = app_row.discovered_job_id
        company = app_row.company
        title = app_row.title

    # Build the ApplicationPackage (does its own DB read).
    package = await prepare_package(
        profile_id=profile_id,
        job_id=discovered_job_id,
        job_url=job_url,
        company=company,
        title=title,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )

    registry = get_registry()
    try:
        next_id = await _next_session_id()
        session = registry.create(
            application_id=application_id,
            platform=package.platform,
            job_url=package.job_url,
            headless=settings.apply_assist_headless,
            force_id=next_id,
        )
    except RegistryError as exc:
        raise ApplyAssistError(str(exc)) from exc

    await _persist_session(session, insert=True)

    browser = _browser_factory(settings.apply_assist_headless)
    session.browser = browser
    agent = PlaywrightApplicationAgent(
        browser=browser,
        emit=_emit,
        screenshot_dir=settings.apply_assist_screenshot_dir,
    )

    async with session.lock:
        try:
            await agent.fill_form(session, package)
        except RunnerError as exc:
            # Persist final FAILED state then bubble.
            await _persist_session(session)
            raise ApplyAssistError(str(exc)) from exc

    await _persist_session(session)
    return session


async def approve(session_id: int) -> ApplyAssistSession:
    registry = get_registry()
    try:
        session = registry.require(session_id)
    except RegistryError as exc:
        raise ApplyAssistError(str(exc)) from exc
    if session.state != STATE_READY_FOR_REVIEW:
        raise ApplyAssistError(
            f"session {session_id} is in state '{session.state}'; expected ready_for_review"
        )
    if session.browser is None:
        raise ApplyAssistError(f"session {session_id} has no live browser")

    settings = get_settings()
    agent = PlaywrightApplicationAgent(
        browser=session.browser,
        emit=_emit,
        screenshot_dir=settings.apply_assist_screenshot_dir,
    )
    async with session.lock:
        try:
            await agent.submit(session)
        except RunnerError as exc:
            await _persist_session(session)
            raise ApplyAssistError(str(exc)) from exc

    # On successful submit, advance the funnel via the canonical path.
    try:
        await update_status(
            settings.sole_user_id,
            session.application_id,
            StatusUpdateRequest(to_status=STATUS_APPLIED, notes="auto-applied via apply-assist"),
        )
    except ApplicationError as exc:
        log.warning(
            "apply_assist.status_advance_failed",
            extra={"application_id": session.application_id, "error": str(exc)},
        )

    await _persist_session(session)
    return session


async def cancel(session_id: int, *, reason: str = "user-cancelled") -> ApplyAssistSession:
    registry = get_registry()
    try:
        session = registry.require(session_id)
    except RegistryError as exc:
        raise ApplyAssistError(str(exc)) from exc
    if session.state in (STATE_SUBMITTED, STATE_FAILED, STATE_CANCELLED):
        return session
    if session.browser is None:
        # Already closed; just mark the row.
        session.state = STATE_CANCELLED
        session.error_message = reason
        session.completed_at = datetime.now(UTC)
        await _emit(session=session, event_type="apply_assist.cancelled", notes=reason)
        await _persist_session(session)
        return session
    settings = get_settings()
    agent = PlaywrightApplicationAgent(
        browser=session.browser,
        emit=_emit,
        screenshot_dir=settings.apply_assist_screenshot_dir,
    )
    async with session.lock:
        await agent.cancel(session, reason=reason)
    await _persist_session(session)
    return session


def get_session(session_id: int) -> ApplyAssistSession | None:
    return get_registry().get(session_id)


async def list_events_for_session(session: ApplyAssistSession) -> list[ApplicationEvent]:
    async with session_scope() as ss:
        rows = (
            await ss.execute(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == session.application_id)
                .where(ApplicationEvent.event_type.like("apply_assist.%"))
                .order_by(ApplicationEvent.occurred_at.asc(), ApplicationEvent.id.asc())
            )
        ).scalars().all()
        for r in rows:
            ss.expunge(r)
        return list(rows)


def serialize_session(session: ApplyAssistSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "application_id": session.application_id,
        "platform": session.platform.value,
        "state": session.state,
        "headless": session.headless,
        "job_url": session.job_url,
        "screenshot_paths": list(session.screenshot_paths),
        "screenshot_count": len(session.screenshot_paths),
        "error_message": session.error_message,
        "started_at": session.started_at.isoformat(),
        "ready_for_review_at": session.ready_for_review_at.isoformat()
        if session.ready_for_review_at
        else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "filled_fields": session.extra.get("filled_fields", []),
        "skipped_fields": session.extra.get("skipped_fields", []),
    }


async def lookup_application_url(application_id: int) -> str | None:
    """Resolve the canonical job URL for an application (cached helper)."""
    async with session_scope() as ss:
        row = await ss.get(Application, application_id)
        if row is None:
            return None
        if row.url:
            return row.url
        if row.discovered_job_id is not None:
            dj = await ss.get(DiscoveredJob, row.discovered_job_id)
            if dj is not None:
                return dj.url
        return None
