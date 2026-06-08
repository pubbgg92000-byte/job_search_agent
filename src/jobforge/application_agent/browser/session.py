"""In-memory registry of live apply-assist browser sessions.

Why in-memory: Phase 3B targets a single-user local deployment. The live
`playwright.async_api.BrowserContext` cannot be serialized to Postgres, so the
authoritative live-session state lives in this process. Durable copies of the
state machine live in `apply_sessions` rows; the registry holds only the
ephemeral things — the browser context, the last-touched timestamp, the
async lock guarding concurrent state mutations on a single session.

Phase 3C: persist to Redis (or a process-shared store) when we add a worker
pool or multi-user.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from jobforge.application_agent.base import ATSPlatform
from jobforge.logging_setup import get_logger

if TYPE_CHECKING:
    from jobforge.agents_phase3.browser import BrowserAgent

log = get_logger("jobforge.apply_assist.session")


STATE_IN_PROGRESS = "in_progress"
STATE_READY_FOR_REVIEW = "ready_for_review"
STATE_SUBMITTED = "submitted"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

ACTIVE_STATES = frozenset({STATE_IN_PROGRESS, STATE_READY_FOR_REVIEW})
TERMINAL_STATES = frozenset({STATE_SUBMITTED, STATE_FAILED, STATE_CANCELLED})


@dataclass
class ApplyAssistSession:
    """Live in-memory state for one apply-assist attempt.

    Mirrors the `apply_sessions` row but additionally holds the live
    `BrowserAgent` instance so submit can reuse the same DOM that the user
    just approved. The `lock` guards concurrent transitions (e.g. an approve
    arriving while a fill is still in flight).
    """

    id: int
    application_id: int
    platform: ATSPlatform
    job_url: str
    headless: bool
    state: str = STATE_IN_PROGRESS
    screenshot_paths: list[str] = field(default_factory=list)
    error_message: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ready_for_review_at: datetime | None = None
    completed_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # Live handle to the browser driving this session. Set during start; cleared
    # on close. Not part of the persisted row.
    browser: BrowserAgent | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_activity_at = datetime.now(UTC)

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class RegistryError(Exception):
    """Raised when a registry invariant is violated (concurrency, lookup)."""


class SessionRegistry:
    """Process-local singleton registry of active apply-assist sessions.

    The registry enforces:
    - At most `max_concurrent` sessions in an active state at any time.
    - Idle sessions older than `ttl_seconds` are reaped on each public call.
    - Terminal sessions are retained for `terminal_grace_seconds` so the
      frontend can fetch their final screenshots / error message before they
      vanish.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 900,
        max_concurrent: int = 1,
        terminal_grace_seconds: int = 600,
    ) -> None:
        self._sessions: dict[int, ApplyAssistSession] = {}
        self._next_id = 1
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_concurrent = max(1, max_concurrent)
        self._terminal_grace = timedelta(seconds=terminal_grace_seconds)

    # ---- introspection ------------------------------------------------

    def __len__(self) -> int:
        return len(self._sessions)

    def all(self) -> list[ApplyAssistSession]:
        return list(self._sessions.values())

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_active)

    def get(self, session_id: int) -> ApplyAssistSession | None:
        return self._sessions.get(session_id)

    def require(self, session_id: int) -> ApplyAssistSession:
        s = self._sessions.get(session_id)
        if s is None:
            raise RegistryError(f"session {session_id} not found")
        return s

    # ---- mutation -----------------------------------------------------

    def create(
        self,
        *,
        application_id: int,
        platform: ATSPlatform,
        job_url: str,
        headless: bool,
        force_id: int | None = None,
    ) -> ApplyAssistSession:
        """Reserve a new active session slot. Raises if cap exceeded."""
        self._reap()
        if self.active_count() >= self._max_concurrent:
            raise RegistryError(
                f"too many active apply-assist sessions "
                f"(cap={self._max_concurrent}); cancel one first"
            )
        sid = force_id if force_id is not None else self._next_id
        if sid in self._sessions:
            raise RegistryError(f"session id {sid} already in registry")
        s = ApplyAssistSession(
            id=sid,
            application_id=application_id,
            platform=platform,
            job_url=job_url,
            headless=headless,
        )
        self._sessions[sid] = s
        self._next_id = max(self._next_id, sid + 1)
        log.info(
            "apply_assist.session.created",
            extra={"session_id": sid, "application_id": application_id},
        )
        return s

    def remove(self, session_id: int) -> None:
        self._sessions.pop(session_id, None)

    # ---- lifecycle ----------------------------------------------------

    def _reap(self) -> None:
        """Drop sessions past TTL (active) or grace (terminal)."""
        now = datetime.now(UTC)
        victims: list[int] = []
        for sid, s in self._sessions.items():
            age = now - s.last_activity_at
            if (s.is_active and age > self._ttl) or (s.is_terminal and age > self._terminal_grace):
                victims.append(sid)
        for sid in victims:
            log.info("apply_assist.session.reaped", extra={"session_id": sid})
            self._sessions.pop(sid, None)


_registry: SessionRegistry | None = None


def get_registry() -> SessionRegistry:
    """Return the process-wide singleton, lazy-initialized from settings."""
    global _registry
    if _registry is None:
        from jobforge.config import get_settings  # local import to avoid cycle

        s = get_settings()
        _registry = SessionRegistry(
            ttl_seconds=s.apply_assist_session_ttl_seconds,
            max_concurrent=s.apply_assist_max_concurrent,
        )
    return _registry


def reset_registry() -> None:
    """Tests use this to wipe the global between cases."""
    global _registry
    _registry = None
