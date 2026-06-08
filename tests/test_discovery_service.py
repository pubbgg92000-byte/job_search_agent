"""Tests for JobDiscoveryService — dedup, upsert, sync-run accounting.

Uses the live Postgres from docker-compose; the adapter is a fake that returns
fixture-defined RawJobs (no network).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from jobforge.db.models import DiscoveredJob, JobSource, JobSyncRun
from jobforge.db.session import session_scope
from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError
from jobforge.discovery.service import sync_adapter, sync_all_sources

pytestmark = pytest.mark.asyncio


class _FakeAdapter(JobSourceAdapter):
    def __init__(self, source: str, jobs: list[RawJob], raises: bool = False) -> None:
        self.source = source
        self._jobs = jobs
        self._raises = raises

    async def fetch_jobs(self) -> list[RawJob]:
        if self._raises:
            raise SourceFetchError(self.source, "boom")
        return list(self._jobs)


def _raw(source: str, jid: str, **over) -> RawJob:
    base = dict(
        source=source,
        source_job_id=jid,
        company="ACME",
        title="Engineer",
        location="Remote",
        remote=True,
        description="desc",
        url=f"https://example.com/{source}/{jid}",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        salary_min=100000,
        salary_max=150000,
        salary_currency="USD",
    )
    base.update(over)
    return RawJob(**base)


async def _wipe_source(source: str) -> None:
    async with session_scope() as session:
        await session.execute(delete(JobSyncRun).where(JobSyncRun.source == source))
        await session.execute(delete(DiscoveredJob).where(DiscoveredJob.source == source))


async def test_first_sync_inserts_all_jobs() -> None:
    src = "fake-insert"
    await _wipe_source(src)
    adapter = _FakeAdapter(src, [_raw(src, "1"), _raw(src, "2")])

    result = await sync_adapter(adapter)

    assert result.discovered == 2
    assert result.inserted == 2
    assert result.updated == 0
    assert result.skipped == 0
    assert result.status == "ok"

    async with session_scope() as session:
        rows = (await session.execute(select(DiscoveredJob).where(DiscoveredJob.source == src))).scalars().all()
        assert len(rows) == 2


async def test_second_sync_dedupes_via_natural_key() -> None:
    src = "fake-dedupe"
    await _wipe_source(src)
    adapter = _FakeAdapter(src, [_raw(src, "1"), _raw(src, "2")])

    await sync_adapter(adapter)
    result2 = await sync_adapter(adapter)

    assert result2.inserted == 0
    assert result2.updated == 2
    async with session_scope() as session:
        n = (await session.execute(select(DiscoveredJob).where(DiscoveredJob.source == src))).scalars().all()
        assert len(n) == 2  # still 2 rows total — not 4


async def test_resync_updates_changed_fields() -> None:
    src = "fake-update"
    await _wipe_source(src)
    await sync_adapter(_FakeAdapter(src, [_raw(src, "1", title="Old Title", salary_max=100000)]))
    await sync_adapter(_FakeAdapter(src, [_raw(src, "1", title="New Title", salary_max=200000)]))

    async with session_scope() as session:
        row = (
            await session.execute(
                select(DiscoveredJob).where(DiscoveredJob.source == src, DiscoveredJob.source_job_id == "1")
            )
        ).scalar_one()
        assert row.title == "New Title"
        assert row.salary_max == 200000


async def test_jobs_missing_url_or_company_are_skipped() -> None:
    src = "fake-skip"
    await _wipe_source(src)
    bad = _raw(src, "1", url="")
    bad_company = _raw(src, "2", company="")
    good = _raw(src, "3")

    result = await sync_adapter(_FakeAdapter(src, [bad, bad_company, good]))

    assert result.skipped == 2
    assert result.inserted == 1


async def test_adapter_error_records_failed_run() -> None:
    src = "fake-err"
    await _wipe_source(src)
    result = await sync_adapter(_FakeAdapter(src, [], raises=True))

    assert result.status == "error"
    assert result.error and "boom" in result.error
    async with session_scope() as session:
        run = (await session.execute(select(JobSyncRun).where(JobSyncRun.source == src))).scalar_one()
        assert run.status == "error"
        assert run.finished_at is not None


async def test_sync_run_records_counts_in_db() -> None:
    src = "fake-counts"
    await _wipe_source(src)
    await sync_adapter(_FakeAdapter(src, [_raw(src, "1"), _raw(src, "2")]))

    async with session_scope() as session:
        run = (
            await session.execute(
                select(JobSyncRun).where(JobSyncRun.source == src).order_by(JobSyncRun.id.desc()).limit(1)
            )
        ).scalar_one()
        assert run.discovered_count == 2
        assert run.inserted_count == 2
        assert run.updated_count == 0
        assert run.status == "ok"
        assert run.finished_at is not None


async def test_sync_all_sources_with_no_enabled_sources_returns_empty() -> None:
    # Disable any existing rows just to be safe in a shared dev DB.
    async with session_scope() as session:
        for js in (await session.execute(select(JobSource))).scalars().all():
            js.enabled = False
    try:
        results = await sync_all_sources()
        assert results == []
    finally:
        # Re-enable so other tests/manual use aren't disrupted.
        async with session_scope() as session:
            for js in (await session.execute(select(JobSource))).scalars().all():
                js.enabled = True
