"""Lightweight in-process asyncio scheduler.

Designed for the single-process MVP. The scheduler runs scheduled jobs based
on a daily target time (08:00 local by default). Tests inject a clock to
exercise tick-by-tick behaviour without sleeping for hours.

Why no APScheduler: extra dep, extra moving parts, and we only need one job.
For Phase 3 distributed workloads, swap this for Celery/RQ/cron.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from jobforge.logging_setup import get_logger, new_request_id

log = get_logger("jobforge.scheduler")


Clock = Callable[[], datetime]
JobFn = Callable[[], Awaitable[Any]]


def _system_clock() -> datetime:
    return datetime.now()


@dataclass
class DailyJob:
    name: str
    run_at: time
    fn: JobFn
    last_ran_on: str | None = None  # ISO date of last successful run


@dataclass
class Scheduler:
    clock: Clock = field(default=_system_clock)
    jobs: list[DailyJob] = field(default_factory=list)

    def add_daily(self, name: str, run_at: time, fn: JobFn) -> None:
        self.jobs.append(DailyJob(name=name, run_at=run_at, fn=fn))

    async def tick(self) -> list[str]:
        """Run any jobs whose target time has passed today and haven't run yet today.

        Returns the list of job names that fired.
        """
        now = self.clock()
        today_iso = now.date().isoformat()
        fired: list[str] = []
        for job in self.jobs:
            if job.last_ran_on == today_iso:
                continue
            scheduled = datetime.combine(now.date(), job.run_at, tzinfo=now.tzinfo)
            if now < scheduled:
                continue
            new_request_id()
            log.info("scheduler.job.start", extra={"job": job.name})
            try:
                await job.fn()
            except Exception as exc:
                log.warning(
                    "scheduler.job.error",
                    extra={"job": job.name, "error": type(exc).__name__},
                )
                # Don't mark last_ran_on on failure — retry on next tick.
                continue
            job.last_ran_on = today_iso
            fired.append(job.name)
            log.info("scheduler.job.done", extra={"job": job.name})
        return fired

    async def run_forever(self, interval_seconds: float = 60.0) -> None:
        """Block forever, ticking every `interval_seconds`."""
        log.info(
            "scheduler.run.start",
            extra={"interval_s": interval_seconds, "jobs": [j.name for j in self.jobs]},
        )
        while True:
            await self.tick()
            await asyncio.sleep(interval_seconds)


def seconds_until_next(now: datetime, run_at: time) -> float:
    """Seconds from `now` until the next occurrence of `run_at`. Handy for logging."""
    scheduled_today = datetime.combine(now.date(), run_at, tzinfo=now.tzinfo)
    if now < scheduled_today:
        return (scheduled_today - now).total_seconds()
    next_day = scheduled_today + timedelta(days=1)
    return (next_day - now).total_seconds()
