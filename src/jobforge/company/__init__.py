"""Company intelligence package.

Architecture (Phase 3B):
- `EnrichmentProvider` ABC — pluggable backends. We ship four:
    * ManualProvider — admin-seeded data from `company_profiles`
    * CompanyWebsiteProvider — careers + homepage scrape
    * WebResearchProvider — structured public-data JSON endpoint
    * NewsProvider — recent news + layoffs classifier
- `CompanyIntelligenceService` — orchestrates providers, merges signals,
  caches results in `company_profiles` for 7 days, computes growth / risk /
  confidence / apply-recommendation deterministically.
- `DeterministicResearchAgent` (in `agents_phase3.company_research`) is a
  thin wrapper that composes the default provider stack.

PRD constraint: unknown values stay null. We never invent industry,
headcount, funding stage, or any score to fill gaps.
"""
from __future__ import annotations

from jobforge.company.base import (
    CompanyEnrichmentData,
    CompanySignal,
    CompanySnapshot,
    EnrichmentProvider,
)
from jobforge.company.scoring import (
    compute_apply_recommendation,
    compute_confidence_score,
    compute_growth_score,
    compute_risk_score,
    render_summary,
)
from jobforge.company.service import (
    CompanyIntelligenceService,
    get_or_enrich,
    reset_default_service,
)

__all__ = [
    "CompanyEnrichmentData",
    "CompanyIntelligenceService",
    "CompanySignal",
    "CompanySnapshot",
    "EnrichmentProvider",
    "compute_apply_recommendation",
    "compute_confidence_score",
    "compute_growth_score",
    "compute_risk_score",
    "get_or_enrich",
    "render_summary",
    "reset_default_service",
]
