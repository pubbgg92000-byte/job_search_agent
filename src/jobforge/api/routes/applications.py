"""Application tracking API endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from jobforge.applications import (
    ApplicationError,
    CreateApplicationRequest,
    StatusUpdateRequest,
    application_to_dict,
    create_application,
    event_to_dict,
    get_application,
    list_applications,
    list_events,
    stats,
    update_status,
)
from jobforge.applications.status import STATUS_SAVED
from jobforge.config import get_settings

router = APIRouter()


class CreatePayload(BaseModel):
    company: str | None = None
    title: str | None = None
    url: str | None = None
    source: str | None = None
    discovered_job_id: int | None = Field(default=None, ge=1)
    artifact_id: int | None = Field(default=None, ge=1)
    job_id: int | None = Field(default=None, ge=1)
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    notes: str | None = None
    status: str = STATUS_SAVED


class StatusPayload(BaseModel):
    status: str
    notes: str | None = None
    occurred_at: datetime | None = None


def _ok(row) -> dict[str, Any]:
    return application_to_dict(row)


@router.post("")
@router.post("/")
async def post_application(payload: CreatePayload) -> dict[str, Any]:
    settings = get_settings()
    try:
        row = await create_application(
            settings.sole_user_id,
            CreateApplicationRequest(
                company=payload.company or "",
                title=payload.title or "",
                url=payload.url,
                source=payload.source,
                discovered_job_id=payload.discovered_job_id,
                artifact_id=payload.artifact_id,
                job_id=payload.job_id,
                recruiter_name=payload.recruiter_name,
                recruiter_email=payload.recruiter_email,
                notes=payload.notes,
                status=payload.status,
            ),
        )
    except ApplicationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ok(row)


@router.get("")
@router.get("/")
async def list_route(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    settings = get_settings()
    total, rows = await list_applications(
        settings.sole_user_id, status=status, limit=limit, offset=offset
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [application_to_dict(r) for r in rows],
    }


@router.get("/stats")
async def stats_route() -> dict[str, Any]:
    settings = get_settings()
    s = await stats(settings.sole_user_id)
    return {
        "total": s.total,
        "by_status": s.by_status,
        "applied": s.applied,
        "interviews": s.interviews,
        "offers": s.offers,
        "rejections": s.rejections,
        "acceptances": s.acceptances,
        "interview_rate": s.interview_rate,
        "offer_rate": s.offer_rate,
        "acceptance_rate": s.acceptance_rate,
    }


@router.get("/{application_id}")
async def get_route(application_id: int) -> dict[str, Any]:
    settings = get_settings()
    row = await get_application(settings.sole_user_id, application_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"application {application_id} not found"
        )
    events = await list_events(application_id)
    return {
        **application_to_dict(row),
        "events": [event_to_dict(e) for e in events],
    }


@router.patch("/{application_id}/status")
async def patch_status_route(
    application_id: int, payload: StatusPayload
) -> dict[str, Any]:
    settings = get_settings()
    try:
        row = await update_status(
            settings.sole_user_id,
            application_id,
            StatusUpdateRequest(
                to_status=payload.status,
                notes=payload.notes,
                occurred_at=payload.occurred_at,
            ),
        )
    except ApplicationError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return _ok(row)
