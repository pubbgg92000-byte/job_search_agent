"""Per-resume analytics.

A "resume version" is a `tailored_artifacts` row. We measure how many
applications used each artifact and how far those applications got — so
the dashboard can surface "this variant produced 4 interviews vs 1 for
the others".
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
from jobforge.db.models import Application, ApplicationEvent, TailoredArtifact
from jobforge.db.session import session_scope


@dataclass(frozen=True)
class ResumeRow:
    artifact_id: int
    model_used: str
    ats_score: int
    created_at: str | None
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
class ResumeReport:
    rows: list[ResumeRow]
    total_artifacts: int

    @property
    def top_performing_artifact(self) -> ResumeRow | None:
        """Highest-performing artifact by interview rate (ties broken by
        absolute interview count, then offers)."""
        with_data = [r for r in self.rows if r.applications > 0]
        if not with_data:
            return None
        return max(
            with_data,
            key=lambda r: (r.interview_rate, r.interviews, r.offers),
        )


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


async def _count_by_artifact_for_event(
    session: AsyncSession, user_id: int, statuses: set[str]
) -> dict[int, int]:
    stmt = (
        select(
            Application.artifact_id,
            func.count(distinct(ApplicationEvent.application_id)),
        )
        .select_from(ApplicationEvent)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(Application.user_id == user_id)
        .where(Application.artifact_id.is_not(None))
        .where(ApplicationEvent.to_status.in_(statuses))
        .group_by(Application.artifact_id)
    )
    rows = (await session.execute(stmt)).all()
    return {int(artifact_id): int(count) for artifact_id, count in rows}


async def _count_applications_by_artifact(
    session: AsyncSession, user_id: int
) -> dict[int, int]:
    stmt = (
        select(
            Application.artifact_id, func.count(Application.id)
        )
        .where(Application.user_id == user_id)
        .where(Application.artifact_id.is_not(None))
        .group_by(Application.artifact_id)
    )
    rows = (await session.execute(stmt)).all()
    return {int(artifact_id): int(count) for artifact_id, count in rows}


async def compute_resume_report(user_id: int) -> ResumeReport:
    async with session_scope() as session:
        artifact_rows = (
            await session.execute(
                select(TailoredArtifact)
                .where(TailoredArtifact.user_id == user_id)
                .order_by(TailoredArtifact.created_at.desc())
            )
        ).scalars().all()
        for r in artifact_rows:
            session.expunge(r)

        applications_by_artifact = await _count_applications_by_artifact(session, user_id)
        applied_events = await _count_by_artifact_for_event(
            session, user_id, _APPLIED_STATUSES
        )
        interview_events = await _count_by_artifact_for_event(
            session, user_id, _INTERVIEW_STATUSES
        )
        offer_events = await _count_by_artifact_for_event(
            session, user_id, _OFFER_STATUSES
        )
        accept_events = await _count_by_artifact_for_event(
            session, user_id, {STATUS_ACCEPTED}
        )

    rows: list[ResumeRow] = []
    for art in artifact_rows:
        # `applications` is the application count tied to this artifact —
        # NOT the event count. The event-count maps are used for the next
        # three fields.
        apps = applications_by_artifact.get(art.id, 0)
        # We tracked applications_submitted via event log because an app
        # can be created without ever hitting applied. Surface both views:
        # applications = total apps using this artifact; interviews/offers
        # = those that ever hit those stages.
        rows.append(
            ResumeRow(
                artifact_id=art.id,
                model_used=art.model_used,
                ats_score=art.ats_score,
                created_at=art.created_at.isoformat() if art.created_at else None,
                applications=apps,
                interviews=interview_events.get(art.id, 0),
                offers=offer_events.get(art.id, 0),
                acceptances=accept_events.get(art.id, 0),
            )
        )

    # Silence unused-variable warning while keeping the value reachable.
    _ = applied_events
    return ResumeReport(rows=rows, total_artifacts=len(rows))


def resume_row_to_dict(r: ResumeRow) -> dict[str, Any]:
    return {
        "artifact_id": r.artifact_id,
        "model_used": r.model_used,
        "ats_score": r.ats_score,
        "created_at": r.created_at,
        "applications": r.applications,
        "interviews": r.interviews,
        "offers": r.offers,
        "acceptances": r.acceptances,
        "interview_rate": r.interview_rate,
        "offer_rate": r.offer_rate,
    }


def resume_report_to_dict(r: ResumeReport) -> dict[str, Any]:
    return {
        "total_artifacts": r.total_artifacts,
        "top_performing_artifact": (
            resume_row_to_dict(r.top_performing_artifact)
            if r.top_performing_artifact
            else None
        ),
        "rows": [resume_row_to_dict(row) for row in r.rows],
    }
