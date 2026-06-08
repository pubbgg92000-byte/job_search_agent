"""JobDiscoveryService — fan out to configured sources, normalize, upsert.

Each source-sync gets its own `job_sync_runs` row so we can observe ingest
volume, error rates, and dedup ratios over time. Upsert uses Postgres'
`ON CONFLICT (source, source_job_id)` to keep the dedup atomic.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.db.models import DiscoveredJob, JobSource, JobSyncRun
from jobforge.db.session import session_scope
from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError
from jobforge.discovery.registry import build_adapter
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.discovery")


@dataclass(frozen=True)
class SyncRunResult:
    source: str
    sync_run_id: int
    discovered: int
    inserted: int
    updated: int
    skipped: int
    status: str
    error: str | None = None


async def _list_enabled_sources(session: AsyncSession) -> list[JobSource]:
    result = await session.execute(select(JobSource).where(JobSource.enabled.is_(True)))
    return list(result.scalars().all())


async def _start_run(session: AsyncSession, source: str, source_id: int | None) -> JobSyncRun:
    run = JobSyncRun(source=source, source_id=source_id)
    session.add(run)
    await session.flush()
    return run


def _upsert_payload(source_id: int | None, raw: RawJob) -> dict[str, object]:
    return {
        "source": raw.source,
        "source_job_id": raw.source_job_id,
        "source_id": source_id,
        "company": raw.company,
        "title": raw.title,
        "location": raw.location,
        "remote": raw.remote,
        "description": raw.description,
        "url": raw.url,
        "posted_at": raw.posted_at,
        "salary_min": raw.salary_min,
        "salary_max": raw.salary_max,
        "salary_currency": raw.salary_currency,
    }


async def _upsert_jobs(
    session: AsyncSession, source_id: int | None, jobs: Iterable[RawJob]
) -> tuple[int, int, int]:
    """Upsert jobs. Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0
    now = datetime.now(UTC)
    for raw in jobs:
        if not raw.url or not raw.title or not raw.company:
            skipped += 1
            continue
        payload = _upsert_payload(source_id, raw)
        stmt = pg_insert(DiscoveredJob).values(**payload, last_seen_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "source_job_id"],
            set_={
                "title": stmt.excluded.title,
                "company": stmt.excluded.company,
                "location": stmt.excluded.location,
                "remote": stmt.excluded.remote,
                "description": stmt.excluded.description,
                "url": stmt.excluded.url,
                "posted_at": stmt.excluded.posted_at,
                "salary_min": stmt.excluded.salary_min,
                "salary_max": stmt.excluded.salary_max,
                "salary_currency": stmt.excluded.salary_currency,
                "last_seen_at": now,
            },
        ).returning(literal_column("(xmax = 0)").label("was_inserted"))
        result = await session.execute(stmt)
        row = result.one()
        if row.was_inserted:
            inserted += 1
        else:
            updated += 1
    return inserted, updated, skipped


async def _sync_one(adapter: JobSourceAdapter, source_id: int | None) -> SyncRunResult:
    async with session_scope() as session:
        run = await _start_run(session, adapter.source, source_id)
        run_id = run.id

    log.info("discovery.source.start", extra={"source": adapter.source, "sync_run_id": run_id})

    try:
        jobs = await adapter.fetch_jobs()
    except SourceFetchError as exc:
        async with session_scope() as session:
            run = await session.get(JobSyncRun, run_id)
            assert run is not None
            run.status = "error"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
        log.warning(
            "discovery.source.error",
            extra={"source": adapter.source, "sync_run_id": run_id, "error": str(exc)},
        )
        return SyncRunResult(
            source=adapter.source,
            sync_run_id=run_id,
            discovered=0,
            inserted=0,
            updated=0,
            skipped=0,
            status="error",
            error=str(exc),
        )

    discovered = len(jobs)
    async with session_scope() as session:
        inserted, updated, skipped = await _upsert_jobs(session, source_id, jobs)
        run = await session.get(JobSyncRun, run_id)
        assert run is not None
        run.status = "ok"
        run.discovered_count = discovered
        run.inserted_count = inserted
        run.updated_count = updated
        run.skipped_count = skipped
        run.finished_at = datetime.now(UTC)

    log.info(
        "discovery.source.done",
        extra={
            "source": adapter.source,
            "sync_run_id": run_id,
            "discovered": discovered,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        },
    )
    return SyncRunResult(
        source=adapter.source,
        sync_run_id=run_id,
        discovered=discovered,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        status="ok",
    )


async def sync_all_sources() -> list[SyncRunResult]:
    """Fan out across all enabled sources concurrently. Returns one result per source."""
    async with session_scope() as session:
        sources = await _list_enabled_sources(session)

    if not sources:
        log.info("discovery.run.empty")
        return []

    pairs: list[tuple[JobSourceAdapter, int]] = []
    for src in sources:
        try:
            adapter = build_adapter(src.kind, src.slug, src.config_json)
        except ValueError as exc:
            log.warning(
                "discovery.source.skip",
                extra={"source_id": src.id, "kind": src.kind, "reason": str(exc)},
            )
            continue
        pairs.append((adapter, src.id))

    log.info("discovery.run.start", extra={"source_count": len(pairs)})
    results = await asyncio.gather(*(_sync_one(a, sid) for a, sid in pairs))
    log.info(
        "discovery.run.done",
        extra={
            "source_count": len(results),
            "total_inserted": sum(r.inserted for r in results),
            "total_updated": sum(r.updated for r in results),
        },
    )
    return list(results)


async def sync_adapter(
    adapter: JobSourceAdapter, source_id: int | None = None
) -> SyncRunResult:
    """Convenience for one-off syncs (e.g. tests or manual triggers)."""
    return await _sync_one(adapter, source_id)
