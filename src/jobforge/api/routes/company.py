"""Company intelligence API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from jobforge.company import get_or_enrich
from jobforge.company.service import CompanyIntelligenceService
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope

router = APIRouter()


class ManualSeedPayload(BaseModel):
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    funding_stage: str | None = None
    remote_policy: str | None = None


def _snapshot_to_dict(snap) -> dict[str, Any]:
    """Convert a CompanySnapshot to the API payload.

    Phase 2B fields are unchanged. Phase 3B fields are added with safe
    defaults (None / empty lists) so this stays additive — existing
    consumers that only read the original 11 fields keep working.
    """
    return {
        # --- Phase 2B (unchanged) ---
        "name": snap.name,
        "website": snap.website,
        "industry": snap.industry,
        "company_size": snap.company_size,
        "funding_stage": snap.funding_stage,
        "remote_policy": snap.remote_policy,
        "growth_score": snap.growth_score,
        "risk_score": snap.risk_score,
        "summary": snap.summary,
        "apply_recommendation": snap.apply_recommendation,
        "last_updated_at": snap.last_updated_at.isoformat()
        if snap.last_updated_at
        else None,
        # --- Phase 3B (additive) ---
        "confidence_score": snap.confidence_score,
        "hiring_velocity_score": snap.hiring_velocity_score,
        "open_roles_count": snap.open_roles_count,
        "tech_stack": list(snap.tech_stack),
        "layoffs_detected": snap.layoffs_detected,
        "news_items": list(snap.news_items),
        "engineering_team_signals": snap.engineering_team_signals,
        "glassdoor_signals": snap.glassdoor_signals,
        "signals": list(snap.signals),
    }


@router.get("/{name}")
async def get_company(name: str) -> dict[str, Any]:
    snap = await get_or_enrich(name)
    return _snapshot_to_dict(snap)


@router.put("/{name}/seed")
async def put_seed(name: str, payload: ManualSeedPayload) -> dict[str, Any]:
    """Admin-style endpoint: write raw enrichment fields directly, then re-score.

    Useful as a stand-in until real enrichment providers ship.
    """
    async with session_scope() as session:
        row = (
            await session.execute(
                select(CompanyProfile).where(CompanyProfile.name == name)
            )
        ).scalar_one_or_none()
        if row is None:
            row = CompanyProfile(name=name)
            session.add(row)
        # Set the raw signals; recompute below by re-enriching.
        row.website = payload.website
        row.industry = payload.industry
        row.company_size = payload.company_size
        row.funding_stage = payload.funding_stage
        row.remote_policy = payload.remote_policy
        await session.flush()

    service = CompanyIntelligenceService()
    snap = await service.enrich(name)
    return _snapshot_to_dict(snap)
