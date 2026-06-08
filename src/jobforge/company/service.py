"""Company intelligence service — cached enrichment + scoring.

Phase 3B: extended to forward `hints` between providers (so a later provider
sees what earlier providers learned), to compute a confidence score, and to
default the TTL to 7 days so deep research isn't re-run on every page load.
The persisted shape on `company_profiles` is unchanged — Phase 3B additions
ride inside the existing `raw_signals` JSON column.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from jobforge.company.base import (
    CompanyEnrichmentData,
    CompanySnapshot,
    EnrichmentProvider,
    merge_enrichment_data,
)
from jobforge.company.providers.manual import ManualProvider
from jobforge.company.scoring import (
    compute_apply_recommendation,
    compute_confidence_score,
    compute_growth_score,
    compute_risk_score,
    render_summary,
)
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.company")

# Phase 3B: research is expensive — cache aggressively (7 days per PRD).
DEFAULT_TTL = timedelta(days=7)

_RAW_SIGNALS_KEY = "phase3b"


def _serialize_phase3b(data: CompanyEnrichmentData, confidence: int | None) -> dict[str, Any]:
    """Capture the Phase 3B aggregates inside the existing raw_signals JSON.

    Keeping this under a single namespaced key keeps existing readers (and
    `ManualProvider`'s admin seed flow) unaffected.
    """
    return {
        "confidence_score": confidence,
        "hiring_velocity_score": data.hiring_velocity_score,
        "open_roles_count": data.open_roles_count,
        "tech_stack": list(data.tech_stack),
        "layoffs_detected": data.layoffs_detected,
        "engineering_team_signals": dict(data.engineering_team_signals),
        "glassdoor_signals": dict(data.glassdoor_signals),
        "news_items": list(data.news_items),
        "signals": [s.to_dict() for s in data.signals],
    }


def _to_snapshot(row: CompanyProfile) -> CompanySnapshot:
    extra: dict[str, Any] = {}
    raw = row.raw_signals or {}
    if isinstance(raw, dict):
        phase3b = raw.get(_RAW_SIGNALS_KEY) or {}
        if isinstance(phase3b, dict):
            extra = phase3b
    return CompanySnapshot(
        name=row.name,
        website=row.website,
        industry=row.industry,
        company_size=row.company_size,
        funding_stage=row.funding_stage,
        remote_policy=row.remote_policy,
        growth_score=row.growth_score,
        risk_score=row.risk_score,
        summary=row.summary,
        apply_recommendation=row.apply_recommendation,
        last_updated_at=row.last_updated_at,
        confidence_score=extra.get("confidence_score"),
        hiring_velocity_score=extra.get("hiring_velocity_score"),
        open_roles_count=extra.get("open_roles_count"),
        tech_stack=tuple(extra.get("tech_stack") or ()),
        layoffs_detected=extra.get("layoffs_detected"),
        news_items=tuple(extra.get("news_items") or ()),
        engineering_team_signals=extra.get("engineering_team_signals") or None,
        glassdoor_signals=extra.get("glassdoor_signals") or None,
        signals=tuple(extra.get("signals") or ()),
    )


class CompanyIntelligenceService:
    def __init__(
        self,
        providers: list[EnrichmentProvider] | None = None,
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        self.providers = providers if providers is not None else [ManualProvider()]
        self.ttl = ttl

    async def _get_row(self, company_name: str) -> CompanyProfile | None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CompanyProfile).where(CompanyProfile.name == company_name)
                )
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def get_cached(
        self, company_name: str, now: datetime | None = None
    ) -> CompanySnapshot | None:
        row = await self._get_row(company_name)
        if row is None:
            return None
        now = now or datetime.now(UTC)
        age = now - row.last_updated_at
        if age < self.ttl:
            log.info(
                "company.cache_hit",
                extra={"company": company_name, "age_seconds": int(age.total_seconds())},
            )
            return _to_snapshot(row)
        return None

    async def enrich(
        self, company_name: str, now: datetime | None = None
    ) -> CompanySnapshot:
        log.info("company.enrich.start", extra={"company": company_name})
        data = CompanyEnrichmentData(name=company_name)
        for provider in self.providers:
            try:
                payload = await provider.enrich(company_name, hints=data)
            except Exception as exc:
                log.warning(
                    "company.provider.error",
                    extra={
                        "company": company_name,
                        "provider": provider.name,
                        "error": type(exc).__name__,
                    },
                )
                continue
            data = merge_enrichment_data(data, payload)

        growth = compute_growth_score(data)
        risk = compute_risk_score(data)
        confidence = compute_confidence_score(data)
        summary = render_summary(data)
        recommend = compute_apply_recommendation(growth, risk)
        now = now or datetime.now(UTC)

        phase3b_payload = _serialize_phase3b(data, confidence)
        # Preserve any non-namespaced raw_signals (admin seeds, legacy data).
        merged_raw: dict[str, Any] = {}
        if data.raw_signals:
            merged_raw.update(data.raw_signals)
        merged_raw[_RAW_SIGNALS_KEY] = phase3b_payload

        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CompanyProfile).where(CompanyProfile.name == company_name)
                )
            ).scalar_one_or_none()
            if row is None:
                row = CompanyProfile(name=company_name)
                session.add(row)
            row.website = data.website
            row.industry = data.industry
            row.company_size = data.company_size
            row.funding_stage = data.funding_stage
            row.remote_policy = data.remote_policy
            row.growth_score = growth
            row.risk_score = risk
            row.summary = summary
            row.apply_recommendation = recommend
            row.raw_signals = merged_raw
            row.last_updated_at = now
            await session.flush()
            snapshot = _to_snapshot(row)

        log.info(
            "company.enrich.done",
            extra={
                "company": company_name,
                "growth": growth,
                "risk": risk,
                "confidence": confidence,
                "recommend": recommend,
            },
        )
        return snapshot

    async def get_or_enrich(
        self, company_name: str, now: datetime | None = None
    ) -> CompanySnapshot:
        cached = await self.get_cached(company_name, now=now)
        if cached is not None:
            return cached
        return await self.enrich(company_name, now=now)


# Convenience: a module-level singleton with the default provider list.
_default_service: CompanyIntelligenceService | None = None


def _get_default_service() -> CompanyIntelligenceService:
    global _default_service
    if _default_service is None:
        # Late import to avoid a circular import at module load.
        from jobforge.company.providers.news import NewsProvider
        from jobforge.company.providers.web_research import WebResearchProvider
        from jobforge.company.providers.website import CompanyWebsiteProvider

        _default_service = CompanyIntelligenceService(
            providers=[
                ManualProvider(),
                CompanyWebsiteProvider(),
                WebResearchProvider(),
                NewsProvider(),
            ]
        )
    return _default_service


def reset_default_service() -> None:
    """Drop the cached singleton. For tests."""
    global _default_service
    _default_service = None


async def get_or_enrich(company_name: str) -> CompanySnapshot:
    return await _get_default_service().get_or_enrich(company_name)
