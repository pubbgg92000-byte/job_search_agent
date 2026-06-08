"""Scheduler tests — tick semantics with an injected clock."""
from __future__ import annotations

from datetime import datetime, time

import pytest

from jobforge.scheduler import Scheduler, seconds_until_next


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.asyncio
async def test_tick_does_not_fire_before_run_time() -> None:
    clock = _FakeClock(datetime(2026, 6, 8, 7, 30))
    s = Scheduler(clock=clock)
    calls: list[str] = []

    async def fn() -> None:
        calls.append("fired")

    s.add_daily("digest", time(hour=8, minute=0), fn)
    fired = await s.tick()
    assert fired == []
    assert calls == []


@pytest.mark.asyncio
async def test_tick_fires_once_at_or_after_run_time() -> None:
    clock = _FakeClock(datetime(2026, 6, 8, 8, 1))
    s = Scheduler(clock=clock)
    calls: list[str] = []

    async def fn() -> None:
        calls.append("fired")

    s.add_daily("digest", time(hour=8, minute=0), fn)
    fired = await s.tick()
    assert fired == ["digest"]
    assert calls == ["fired"]

    # Second tick same day: no-op.
    fired2 = await s.tick()
    assert fired2 == []
    assert calls == ["fired"]


@pytest.mark.asyncio
async def test_tick_fires_again_next_day() -> None:
    clock = _FakeClock(datetime(2026, 6, 8, 8, 1))
    s = Scheduler(clock=clock)
    calls: list[str] = []

    async def fn() -> None:
        calls.append("fired")

    s.add_daily("digest", time(hour=8, minute=0), fn)
    await s.tick()  # day 1
    clock.now = datetime(2026, 6, 9, 8, 1)  # day 2
    fired = await s.tick()
    assert fired == ["digest"]
    assert calls == ["fired", "fired"]


@pytest.mark.asyncio
async def test_tick_retries_failed_job_until_success() -> None:
    clock = _FakeClock(datetime(2026, 6, 8, 8, 1))
    s = Scheduler(clock=clock)
    attempts = {"n": 0}

    async def flaky() -> None:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("first attempt fails")

    s.add_daily("digest", time(hour=8, minute=0), flaky)
    fired1 = await s.tick()
    assert fired1 == []  # error → not marked
    assert attempts["n"] == 1
    # Second tick on the same day should retry.
    fired2 = await s.tick()
    assert fired2 == ["digest"]
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_multiple_jobs_fire_independently() -> None:
    clock = _FakeClock(datetime(2026, 6, 8, 9, 1))
    s = Scheduler(clock=clock)
    fired_names: list[str] = []

    async def make_fn(name: str):
        async def _f() -> None:
            fired_names.append(name)
        return _f

    f1 = await make_fn("digest")
    f2 = await make_fn("cleanup")
    s.add_daily("digest", time(hour=8, minute=0), f1)
    s.add_daily("cleanup", time(hour=9, minute=0), f2)

    fired = await s.tick()
    assert set(fired) == {"digest", "cleanup"}


def test_seconds_until_next_today_when_before_run_time() -> None:
    now = datetime(2026, 6, 8, 7, 30)
    s = seconds_until_next(now, time(hour=8, minute=0))
    assert s == 30 * 60


def test_seconds_until_next_tomorrow_when_after_run_time() -> None:
    now = datetime(2026, 6, 8, 9, 0)
    s = seconds_until_next(now, time(hour=8, minute=0))
    # 23 hours to tomorrow 8am
    assert s == 23 * 3600
