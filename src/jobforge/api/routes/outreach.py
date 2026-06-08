"""Recruiter outreach API endpoints (Phase 3D)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from jobforge.applications import ApplicationError
from jobforge.config import get_settings
from jobforge.db.models import Profile
from jobforge.db.session import session_scope
from jobforge.outreach import (
    ALL_KINDS,
    CreateCampaignRequest,
    DraftMessageRequest,
    MessageContext,
    MessageError,
    OutreachError,
    StatusUpdateRequest,
    UpsertContactRequest,
    campaign_to_dict,
    compute_metrics,
    contact_to_dict,
    create_campaign,
    delete_contact,
    discover_contacts,
    draft_message,
    event_to_dict,
    generate_message,
    get_campaign,
    get_contact,
    list_campaigns,
    list_contacts,
    list_due_follow_ups,
    list_events,
    list_messages,
    list_recent_replies,
    mark_sent,
    message_row_to_dict,
    message_to_dict,
    metrics_to_dict,
    update_status,
    upsert_contact,
)
from jobforge.outreach.contacts import VALID_KINDS
from jobforge.outreach.providers import ManualProvider, WebResearchProvider
from jobforge.outreach.providers.base import DiscoveredContact
from jobforge.outreach.status import ALL_STATUSES

router = APIRouter()


# ---------------- payload models ----------------


class UpsertContactPayload(BaseModel):
    company: str
    name: str
    kind: str = "recruiter"
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str = "manual"
    confidence: int = Field(75, ge=0, le=100)
    notes: str | None = None


class DiscoverContactsPayload(BaseModel):
    company: str
    seeds: list[UpsertContactPayload] | None = None
    use_web_research: bool = False


class CreateCampaignPayload(BaseModel):
    contact_id: int = Field(..., ge=1)
    application_id: int | None = Field(None, ge=1)
    interview_plan_id: int | None = Field(None, ge=1)
    goal: str = "initial_outreach"
    notes: str | None = None


class StatusPayload(BaseModel):
    status: str
    notes: str | None = None
    occurred_at: datetime | None = None


class DraftMessagePayload(BaseModel):
    kind: str
    channel: str | None = None
    company: str | None = None
    contact_name: str | None = None
    contact_kind: str | None = None
    contact_role: str | None = None
    role_title: str | None = None
    candidate_name: str | None = None
    candidate_headline: str | None = None
    candidate_years_experience: int | None = None
    top_skills: list[str] | None = None
    matched_skills: list[str] | None = None
    company_summary: str | None = None
    company_industry: str | None = None
    referral_target: str | None = None
    previous_message_kind: str | None = None
    days_since_last_message: int | None = None
    interview_topic: str | None = None
    interview_round: str | None = None


class MarkSentPayload(BaseModel):
    occurred_at: datetime | None = None
    follow_up_in_days: int = Field(7, ge=0, le=60)
    notes: str | None = None


# ---------------- helpers ----------------


async def _latest_profile_json(user_id: int) -> dict[str, Any]:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(desc(Profile.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return {}
        session.expunge(row)
        return row.parsed_json or {}


def _years_experience(profile: dict[str, Any]) -> int | None:
    # Cheap heuristic: count of experience entries — used only when the
    # profile doesn't have an explicit `years_experience` field.
    explicit = profile.get("years_experience")
    if isinstance(explicit, (int, float)) and explicit > 0:
        return int(explicit)
    experience = profile.get("experience")
    if isinstance(experience, list) and experience:
        # Floor at 2 years per role unless field specifies otherwise — keeps
        # the message honest about "I'm a recent grad" vs senior.
        guess = max(1, len(experience))
        return guess
    return None


def _build_context_from_payload(
    payload: DraftMessagePayload, profile: dict[str, Any]
) -> MessageContext:
    return MessageContext(
        company=(payload.company or "").strip(),
        contact_name=(payload.contact_name or "").strip(),
        contact_kind=payload.contact_kind or "recruiter",
        contact_role=payload.contact_role,
        role_title=payload.role_title,
        candidate_name=payload.candidate_name or profile.get("name"),
        candidate_headline=payload.candidate_headline,
        candidate_years_experience=payload.candidate_years_experience
        or _years_experience(profile),
        top_skills=payload.top_skills or list(profile.get("skills") or [])[:10],
        matched_skills=payload.matched_skills or [],
        company_summary=payload.company_summary,
        company_industry=payload.company_industry,
        referral_target=payload.referral_target,
        previous_message_kind=payload.previous_message_kind,
        days_since_last_message=payload.days_since_last_message,
        interview_topic=payload.interview_topic,
        interview_round=payload.interview_round,
    )


# ---------------- contacts ----------------


@router.post("/contacts")
async def upsert_contact_route(payload: UpsertContactPayload) -> dict[str, Any]:
    settings = get_settings()
    try:
        row = await upsert_contact(
            settings.sole_user_id,
            UpsertContactRequest(
                company=payload.company,
                name=payload.name,
                kind=payload.kind,
                role=payload.role,
                linkedin_url=payload.linkedin_url,
                email=payload.email,
                phone=payload.phone,
                source=payload.source,
                confidence=payload.confidence,
                notes=payload.notes,
            ),
        )
    except OutreachError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return contact_to_dict(row)


@router.get("/contacts")
async def list_contacts_route(
    company: str | None = None,
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    settings = get_settings()
    if kind and kind not in VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown kind '{kind}' (allowed: {sorted(VALID_KINDS)})",
        )
    total, rows = await list_contacts(
        settings.sole_user_id, company=company, kind=kind, limit=limit, offset=offset
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [contact_to_dict(r) for r in rows],
    }


@router.get("/contacts/{contact_id}")
async def get_contact_route(contact_id: int) -> dict[str, Any]:
    settings = get_settings()
    row = await get_contact(settings.sole_user_id, contact_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"contact {contact_id} not found")
    return contact_to_dict(row)


@router.delete("/contacts/{contact_id}")
async def delete_contact_route(contact_id: int) -> dict[str, Any]:
    settings = get_settings()
    ok = await delete_contact(settings.sole_user_id, contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"contact {contact_id} not found")
    return {"deleted": contact_id}


@router.post("/contacts/discover")
async def discover_contacts_route(payload: DiscoverContactsPayload) -> dict[str, Any]:
    settings = get_settings()
    providers: list[Any] = []
    if payload.seeds:
        providers.append(
            ManualProvider(
                seeds=[
                    DiscoveredContact(
                        name=s.name,
                        kind=s.kind,
                        role=s.role,
                        linkedin_url=s.linkedin_url,
                        email=s.email,
                        phone=s.phone,
                        source=s.source or "manual",
                        confidence=s.confidence,
                        notes=s.notes,
                    )
                    for s in payload.seeds
                ]
            )
        )
    if payload.use_web_research:
        providers.append(WebResearchProvider())
    if not providers:
        providers.append(ManualProvider())
    try:
        rows = await discover_contacts(
            settings.sole_user_id, payload.company, providers=providers
        )
    except OutreachError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [contact_to_dict(r) for r in rows], "total": len(rows)}


# ---------------- campaigns ----------------


@router.post("/campaigns")
async def create_campaign_route(payload: CreateCampaignPayload) -> dict[str, Any]:
    settings = get_settings()
    if payload.goal not in ALL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"invalid goal '{payload.goal}' (allowed: {list(ALL_KINDS)})",
        )
    try:
        row = await create_campaign(
            settings.sole_user_id,
            CreateCampaignRequest(
                contact_id=payload.contact_id,
                application_id=payload.application_id,
                interview_plan_id=payload.interview_plan_id,
                goal=payload.goal,
                notes=payload.notes,
            ),
        )
    except OutreachError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return campaign_to_dict(row)


@router.get("/campaigns")
async def list_campaigns_route(
    status: str | None = None,
    contact_id: int | None = Query(None, ge=1),
    application_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    if status and status not in ALL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown status '{status}' (allowed: {list(ALL_STATUSES)})",
        )
    settings = get_settings()
    total, rows = await list_campaigns(
        settings.sole_user_id,
        status=status,
        contact_id=contact_id,
        application_id=application_id,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [campaign_to_dict(r) for r in rows],
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign_route(campaign_id: int) -> dict[str, Any]:
    settings = get_settings()
    row = await get_campaign(settings.sole_user_id, campaign_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"campaign {campaign_id} not found")
    events = await list_events(campaign_id)
    msgs = await list_messages(campaign_id)
    return {
        **campaign_to_dict(row),
        "events": [event_to_dict(e) for e in events],
        "messages": [message_row_to_dict(m) for m in msgs],
    }


@router.patch("/campaigns/{campaign_id}/status")
async def patch_campaign_status_route(
    campaign_id: int, payload: StatusPayload
) -> dict[str, Any]:
    settings = get_settings()
    try:
        row = await update_status(
            settings.sole_user_id,
            campaign_id,
            StatusUpdateRequest(
                to_status=payload.status,
                notes=payload.notes,
                occurred_at=payload.occurred_at,
            ),
        )
    except OutreachError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return campaign_to_dict(row)


# ---------------- messages ----------------


@router.post("/campaigns/{campaign_id}/messages")
async def draft_message_route(
    campaign_id: int, payload: DraftMessagePayload
) -> dict[str, Any]:
    settings = get_settings()
    profile = await _latest_profile_json(settings.sole_user_id)
    ctx = _build_context_from_payload(payload, profile)
    # If the payload omitted contact_name, pull it from the campaign's contact.
    if not ctx.contact_name or not ctx.company:
        campaign = await get_campaign(settings.sole_user_id, campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=404, detail=f"campaign {campaign_id} not found"
            )
        contact = await get_contact(settings.sole_user_id, campaign.contact_id)
        if contact is None:
            raise HTTPException(
                status_code=404, detail=f"contact {campaign.contact_id} not found"
            )
        if not ctx.contact_name:
            ctx = _replace(ctx, contact_name=contact.name)
        if not ctx.company:
            ctx = _replace(ctx, company=contact.company)
    try:
        row = await draft_message(
            settings.sole_user_id,
            campaign_id,
            DraftMessageRequest(kind=payload.kind, ctx=ctx, channel=payload.channel),
        )
    except OutreachError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    except MessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return message_row_to_dict(row)


def _replace(ctx: MessageContext, **kwargs: Any) -> MessageContext:
    from dataclasses import replace

    return replace(ctx, **kwargs)


@router.post("/messages/preview")
async def preview_message_route(payload: DraftMessagePayload) -> dict[str, Any]:
    """Render a message WITHOUT persisting it. Useful for the UI's compose view."""
    settings = get_settings()
    profile = await _latest_profile_json(settings.sole_user_id)
    ctx = _build_context_from_payload(payload, profile)
    try:
        drafted = generate_message(payload.kind, ctx)
    except MessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return message_to_dict(drafted)


@router.post("/campaigns/{campaign_id}/messages/{message_id}/sent")
async def mark_sent_route(
    campaign_id: int, message_id: int, payload: MarkSentPayload | None = None
) -> dict[str, Any]:
    settings = get_settings()
    payload = payload or MarkSentPayload()
    try:
        row = await mark_sent(
            settings.sole_user_id,
            campaign_id,
            message_id,
            occurred_at=payload.occurred_at,
            notes=payload.notes,
            follow_up_in_days=payload.follow_up_in_days,
        )
    except OutreachError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return campaign_to_dict(row)


# ---------------- dashboard ----------------


@router.get("/dashboard")
async def outreach_dashboard_route(limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    settings = get_settings()
    metrics = await compute_metrics(settings.sole_user_id)
    due = await list_due_follow_ups(settings.sole_user_id, limit=limit)
    replies = await list_recent_replies(settings.sole_user_id, limit=limit)
    _, contacts = await list_contacts(settings.sole_user_id, limit=limit, offset=0)
    _, recent_campaigns = await list_campaigns(
        settings.sole_user_id, limit=limit, offset=0
    )
    return {
        "metrics": metrics_to_dict(metrics),
        "due_follow_ups": [campaign_to_dict(c) for c in due],
        "recent_replies": [campaign_to_dict(c) for c in replies],
        "recent_contacts": [contact_to_dict(c) for c in contacts],
        "recent_campaigns": [campaign_to_dict(c) for c in recent_campaigns],
    }


@router.get("/metrics")
async def metrics_route() -> dict[str, Any]:
    settings = get_settings()
    metrics = await compute_metrics(settings.sole_user_id)
    return metrics_to_dict(metrics)


@router.get("/follow-ups")
async def follow_ups_route(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    settings = get_settings()
    rows = await list_due_follow_ups(settings.sole_user_id, limit=limit)
    return {"items": [campaign_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/replies")
async def replies_route(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    settings = get_settings()
    rows = await list_recent_replies(settings.sole_user_id, limit=limit)
    return {"items": [campaign_to_dict(r) for r in rows], "total": len(rows)}


# Re-raise so downstream code can still differentiate.
_ = ApplicationError
