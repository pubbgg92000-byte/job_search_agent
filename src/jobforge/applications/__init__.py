"""Application tracking service — CRUD, status transitions, event log, stats."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.applications.status import (
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_SAVED,
    is_forward_transition,
    is_valid_status,
)
from jobforge.db.models import (
    Application,
    ApplicationEvent,
    DiscoveredJob,
)
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.applications")


class ApplicationError(Exception):
    """Service-level error (e.g. invalid status, missing application)."""


@dataclass
class CreateApplicationRequest:
    company: str
    title: str
    url: str | None = None
    source: str | None = None
    discovered_job_id: int | None = None
    artifact_id: int | None = None
    job_id: int | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    notes: str | None = None
    status: str = STATUS_SAVED


@dataclass
class StatusUpdateRequest:
    to_status: str
    notes: str | None = None
    occurred_at: datetime | None = None


@dataclass
class ApplicationStats:
    total: int
    by_status: dict[str, int]
    applied: int
    interviews: int
    offers: int
    rejections: int
    acceptances: int
    interview_rate: float
    offer_rate: float
    acceptance_rate: float


async def _hydrate_from_discovered_job(
    session: AsyncSession, req: CreateApplicationRequest
) -> CreateApplicationRequest:
    """If discovered_job_id is set and url/company/title are blank, pull them in."""
    if req.discovered_job_id is None:
        return req
    job = await session.get(DiscoveredJob, req.discovered_job_id)
    if job is None:
        raise ApplicationError(
            f"discovered_job_id={req.discovered_job_id} not found"
        )
    return CreateApplicationRequest(
        company=req.company or job.company,
        title=req.title or job.title,
        url=req.url or job.url,
        source=req.source or job.source,
        discovered_job_id=req.discovered_job_id,
        artifact_id=req.artifact_id,
        job_id=req.job_id,
        recruiter_name=req.recruiter_name,
        recruiter_email=req.recruiter_email,
        notes=req.notes,
        status=req.status,
    )


async def create_application(
    user_id: int, req: CreateApplicationRequest
) -> Application:
    if not is_valid_status(req.status):
        raise ApplicationError(f"invalid status '{req.status}'")

    async with session_scope() as session:
        req = await _hydrate_from_discovered_job(session, req)
        if not req.company or not req.title:
            raise ApplicationError("company and title are required")

        app_row = Application(
            user_id=user_id,
            job_id=req.job_id,
            artifact_id=req.artifact_id,
            discovered_job_id=req.discovered_job_id,
            company=req.company,
            title=req.title,
            url=req.url,
            source=req.source,
            recruiter_name=req.recruiter_name,
            recruiter_email=req.recruiter_email,
            status=req.status,
            notes=req.notes,
        )
        if req.status == STATUS_APPLIED:
            app_row.applied_at = datetime.now(UTC)
        session.add(app_row)
        await session.flush()

        session.add(
            ApplicationEvent(
                application_id=app_row.id,
                event_type="created",
                to_status=req.status,
                notes=req.notes,
            )
        )
        await session.flush()
        log.info(
            "application.created",
            extra={
                "application_id": app_row.id,
                "company": app_row.company,
                "title": app_row.title,
                "status": app_row.status,
            },
        )
        # Refresh all columns (including server-side defaults like created_at /
        # last_updated) before expunging so the detached object stays usable.
        await session.refresh(app_row)
        session.expunge(app_row)
        return app_row


async def list_applications(
    user_id: int,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Application]]:
    async with session_scope() as session:
        filters = [Application.user_id == user_id]
        if status:
            filters.append(Application.status == status)
        total = int(
            (await session.execute(select(func.count(Application.id)).where(*filters))).scalar_one()
        )
        rows = (
            await session.execute(
                select(Application)
                .where(*filters)
                .order_by(Application.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return total, list(rows)


async def get_application(user_id: int, application_id: int) -> Application | None:
    async with session_scope() as session:
        row = await session.get(Application, application_id)
        if row is None or row.user_id != user_id:
            return None
        session.expunge(row)
        return row


async def list_events(application_id: int) -> list[ApplicationEvent]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application_id)
                .order_by(ApplicationEvent.occurred_at.asc(), ApplicationEvent.id.asc())
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
        return list(rows)


async def update_status(
    user_id: int, application_id: int, req: StatusUpdateRequest
) -> Application:
    if not is_valid_status(req.to_status):
        raise ApplicationError(f"invalid status '{req.to_status}'")

    async with session_scope() as session:
        app_row = await session.get(Application, application_id)
        if app_row is None or app_row.user_id != user_id:
            raise ApplicationError(f"application {application_id} not found")
        from_status = app_row.status
        if from_status == req.to_status:
            await session.refresh(app_row)
            session.expunge(app_row)
            return app_row

        event_type = (
            "status_change"
            if is_forward_transition(from_status, req.to_status)
            else "status_change_unusual"
        )

        app_row.status = req.to_status
        if req.to_status == STATUS_APPLIED and app_row.applied_at is None:
            app_row.applied_at = req.occurred_at or datetime.now(UTC)

        session.add(
            ApplicationEvent(
                application_id=app_row.id,
                event_type=event_type,
                from_status=from_status,
                to_status=req.to_status,
                notes=req.notes,
                occurred_at=req.occurred_at or datetime.now(UTC),
            )
        )
        await session.flush()
        log.info(
            "application.status_change",
            extra={
                "application_id": app_row.id,
                "from": from_status,
                "to": req.to_status,
                "unusual": event_type == "status_change_unusual",
            },
        )
        await session.refresh(app_row)
        session.expunge(app_row)
        return app_row


async def stats(user_id: int) -> ApplicationStats:
    """Funnel stats — cumulative across the event log.

    `applied` / `interviews` / `offers` count distinct applications that ever
    reached each stage, not just those currently in it. An application that
    advanced applied → interview → rejected still contributes 1 to both
    `applied` and `interviews`.

    Rates are computed against the parent stage (interview_rate = interviews
    / applied, offer_rate = offers / applied, acceptance_rate = accepted / offers).
    """
    interview_statuses = {
        STATUS_INTERVIEW_SCHEDULED,
        STATUS_INTERVIEW_COMPLETED,
        STATUS_OFFER,
        STATUS_ACCEPTED,
        "declined",
    }
    offer_statuses = {STATUS_OFFER, STATUS_ACCEPTED, "declined"}
    applied_statuses = {
        STATUS_APPLIED,
        *interview_statuses,
    }

    async with session_scope() as session:
        result = await session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user_id)
            .group_by(Application.status)
        )
        by_status: dict[str, int] = {s: int(c) for s, c in result.all()}

        async def _reached(targets: set[str]) -> int:
            stmt = (
                select(func.count(func.distinct(ApplicationEvent.application_id)))
                .select_from(ApplicationEvent)
                .join(Application, Application.id == ApplicationEvent.application_id)
                .where(Application.user_id == user_id)
                .where(ApplicationEvent.to_status.in_(targets))
            )
            return int((await session.execute(stmt)).scalar_one() or 0)

        applied = await _reached(applied_statuses)
        interviews = await _reached(interview_statuses)
        offers = await _reached(offer_statuses)

    total = sum(by_status.values())
    rejections = by_status.get(STATUS_REJECTED, 0)
    acceptances = by_status.get(STATUS_ACCEPTED, 0)

    def _rate(n: int, d: int) -> float:
        return round(n / d, 4) if d > 0 else 0.0

    return ApplicationStats(
        total=total,
        by_status=by_status,
        applied=applied,
        interviews=interviews,
        offers=offers,
        rejections=rejections,
        acceptances=acceptances,
        interview_rate=_rate(interviews, applied),
        offer_rate=_rate(offers, applied),
        acceptance_rate=_rate(acceptances, offers),
    )


def application_to_dict(row: Application) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "status": row.status,
        "company": row.company,
        "title": row.title,
        "url": row.url,
        "source": row.source,
        "discovered_job_id": row.discovered_job_id,
        "job_id": row.job_id,
        "artifact_id": row.artifact_id,
        "recruiter_name": row.recruiter_name,
        "recruiter_email": row.recruiter_email,
        "notes": row.notes,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_updated": row.last_updated.isoformat() if row.last_updated else None,
    }


def event_to_dict(row: ApplicationEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "event_type": row.event_type,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "notes": row.notes,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
    }
