"""Manual enrichment provider — reads admin-seeded data straight from `company_profiles`.

This is the only provider we ship today. Real third-party providers (Clearbit,
Crunchbase, etc.) implement the same `EnrichmentProvider` ABC and slot in.
"""
from __future__ import annotations

from sqlalchemy import select

from jobforge.company.base import CompanyEnrichmentData, EnrichmentProvider
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope


class ManualProvider(EnrichmentProvider):
    name = "manual"

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CompanyProfile).where(CompanyProfile.name == company_name)
                )
            ).scalar_one_or_none()
            if row is None:
                return CompanyEnrichmentData(name=company_name)
            return CompanyEnrichmentData(
                name=row.name,
                website=row.website,
                industry=row.industry,
                company_size=row.company_size,
                funding_stage=row.funding_stage,
                remote_policy=row.remote_policy,
                raw_signals=row.raw_signals or {},
            )
