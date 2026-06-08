"""Per-source application + interview + offer breakdown.

`Application.source` is the discovery source name when an application is
tied to a `DiscoveredJob` (greenhouse/lever/ashby/remoteok/remotive/wwr)
or `manual` when the user added the row directly. We compute per-source
counts cumulatively over the event log so a closed application still
contributes to whatever stages it touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.applications.status import (
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_DECLINED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
)
from jobforge.db.models import Application, ApplicationEvent
from jobforge.db.session import session_scope

# PRD source set. We always emit a row per supported source even when the
# count is zero so the dashboard can render a stable list.
SUPPORTED_SOURCES = (
    "greenhouse",
    "lever",
    "ashby",
    "remoteok",
    "remotive",
    "wwr",
)


@dataclass(frozen=True)
class SourceRow:
    source: str
    applications: int
    interviews: int
    offers: int
    acceptances: int

    @property
    def interview_rate(self) -> float:
        return (
            round(self.interviews / self.applications, 4) if self.applications else 0.0
        )

    @property
    def offer_rate(self) -> float:
        return round(self.offers / self.applications, 4) if self.applications else 0.0


@dataclass(frozen=True)
class SourceReport:
    rows: list[SourceRow]
    total_applications: int

    @property
    def best_source_for_interviews(self) -> str | None:
        with_data = [r for r in self.rows if r.applications > 0]
        if not with_data:
            return None
        return max(with_data, key=lambda r: (r.interview_rate, r.applications)).source


_APPLIED_STATUSES = {
    STATUS_APPLIED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_INTERVIEW_STATUSES = {
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
}
_OFFER_STATUSES = {STATUS_OFFER, STATUS_ACCEPTED, STATUS_DECLINED}


async def _count_by_source_for_event(
    session: AsyncSession, user_id: int, statuses: set[str]
) -> dict[str, int]:
    """Distinct applications per source that ever hit a target status."""
    stmt = (
        select(
            Application.source,
            func.count(distinct(ApplicationEvent.application_id)),
        )
        .select_from(ApplicationEvent)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(Application.user_id == user_id)
        .where(ApplicationEvent.to_status.in_(statuses))
        .group_by(Application.source)
    )
    rows = (await session.execute(stmt)).all()
    out: dict[str, int] = {}
    for source, count in rows:
        key = (source or "manual").lower()
        out[key] = int(count)
    return out


async def compute_source_report(user_id: int) -> SourceReport:
    async with session_scope() as session:
        applied = await _count_by_source_for_event(session, user_id, _APPLIED_STATUSES)
        interviews = await _count_by_source_for_event(
            session, user_id, _INTERVIEW_STATUSES
        )
        offers = await _count_by_source_for_event(session, user_id, _OFFER_STATUSES)
        acceptances = await _count_by_source_for_event(
            session, user_id, {STATUS_ACCEPTED}
        )

    # Build the result row-set: always include every supported source plus
    # any extra source we saw (e.g. `manual`).
    keys: set[str] = set(SUPPORTED_SOURCES)
    keys.update(applied)
    keys.update(interviews)
    keys.update(offers)
    keys.update(acceptances)

    rows: list[SourceRow] = []
    for key in sorted(keys):
        rows.append(
            SourceRow(
                source=key,
                applications=applied.get(key, 0),
                interviews=interviews.get(key, 0),
                offers=offers.get(key, 0),
                acceptances=acceptances.get(key, 0),
            )
        )

    total = sum(r.applications for r in rows)
    return SourceReport(rows=rows, total_applications=total)


def source_row_to_dict(r: SourceRow) -> dict[str, Any]:
    return {
        "source": r.source,
        "applications": r.applications,
        "interviews": r.interviews,
        "offers": r.offers,
        "acceptances": r.acceptances,
        "interview_rate": r.interview_rate,
        "offer_rate": r.offer_rate,
    }


def source_report_to_dict(r: SourceReport) -> dict[str, Any]:
    return {
        "total_applications": r.total_applications,
        "best_source_for_interviews": r.best_source_for_interviews,
        "rows": [source_row_to_dict(row) for row in r.rows],
    }
