"""In-memory session registry: lifecycle, concurrency cap, TTL eviction."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jobforge.application_agent.base import ATSPlatform
from jobforge.application_agent.browser.session import (
    STATE_FAILED,
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    RegistryError,
    SessionRegistry,
)


def _make_registry(**kw: int) -> SessionRegistry:
    return SessionRegistry(
        ttl_seconds=kw.get("ttl_seconds", 900),
        max_concurrent=kw.get("max_concurrent", 1),
        terminal_grace_seconds=kw.get("terminal_grace_seconds", 600),
    )


def _create(reg: SessionRegistry, *, app_id: int = 1, force_id: int | None = None) -> int:
    s = reg.create(
        application_id=app_id,
        platform=ATSPlatform.GREENHOUSE,
        job_url="https://boards.greenhouse.io/x/jobs/1",
        headless=True,
        force_id=force_id,
    )
    return s.id


def test_create_assigns_incrementing_ids() -> None:
    reg = _make_registry(max_concurrent=10)
    a = _create(reg, app_id=1)
    b = _create(reg, app_id=2)
    assert b == a + 1


def test_force_id_is_honored() -> None:
    reg = _make_registry()
    sid = _create(reg, force_id=42)
    assert sid == 42


def test_force_id_collision_raises() -> None:
    reg = _make_registry(max_concurrent=10)
    _create(reg, force_id=5)
    with pytest.raises(RegistryError):
        _create(reg, force_id=5)


def test_concurrency_cap_blocks_second_active_session() -> None:
    reg = _make_registry(max_concurrent=1)
    _create(reg, app_id=1)
    with pytest.raises(RegistryError):
        _create(reg, app_id=2)


def test_concurrency_cap_allows_after_first_terminates() -> None:
    reg = _make_registry(max_concurrent=1)
    sid = _create(reg, app_id=1)
    s = reg.require(sid)
    s.state = STATE_SUBMITTED
    # New active session may now start.
    new_id = _create(reg, app_id=2)
    assert new_id != sid


def test_ttl_eviction_drops_idle_active_session() -> None:
    reg = _make_registry(ttl_seconds=1, max_concurrent=2)
    sid = _create(reg, app_id=1)
    s = reg.require(sid)
    s.last_activity_at = datetime.now(UTC) - timedelta(seconds=5)
    # New create triggers the reap; old session disappears.
    _create(reg, app_id=2)
    assert reg.get(sid) is None


def test_terminal_grace_keeps_recent_finished_session() -> None:
    reg = _make_registry(max_concurrent=2, terminal_grace_seconds=600)
    sid = _create(reg)
    s = reg.require(sid)
    s.state = STATE_SUBMITTED
    # Trigger reap via another create.
    _create(reg, app_id=2)
    assert reg.get(sid) is not None


def test_require_raises_for_unknown_id() -> None:
    reg = _make_registry()
    with pytest.raises(RegistryError):
        reg.require(9999)


def test_remove_is_idempotent() -> None:
    reg = _make_registry()
    sid = _create(reg)
    reg.remove(sid)
    reg.remove(sid)  # second call must not raise
    assert reg.get(sid) is None


def test_active_count_reflects_state() -> None:
    reg = _make_registry(max_concurrent=3)
    a = _create(reg, app_id=1)
    b = _create(reg, app_id=2)
    reg.require(b).state = STATE_FAILED
    assert reg.active_count() == 1
    reg.require(a).state = STATE_READY_FOR_REVIEW
    assert reg.active_count() == 1  # still active


def test_is_terminal_helpers() -> None:
    reg = _make_registry()
    sid = _create(reg)
    s = reg.require(sid)
    assert s.is_active and not s.is_terminal
    s.state = STATE_SUBMITTED
    assert s.is_terminal and not s.is_active


def test_all_returns_snapshot_list() -> None:
    reg = _make_registry(max_concurrent=2)
    _create(reg, app_id=1)
    _create(reg, app_id=2)
    out = reg.all()
    assert len(out) == 2
    assert all(s.platform == ATSPlatform.GREENHOUSE for s in out)
