"""Tests for company intelligence — scoring, summary rendering, service caching."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from jobforge.company import (
    CompanyEnrichmentData,
    CompanyIntelligenceService,
    EnrichmentProvider,
    compute_apply_recommendation,
    compute_growth_score,
    compute_risk_score,
    render_summary,
)
from jobforge.company.base import merge_enrichment_data
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope


async def _wipe(name: str) -> None:
    async with session_scope() as session:
        await session.execute(
            delete(CompanyProfile).where(CompanyProfile.name == name)
        )


# --------------------------- scoring --------------------------------------


def test_growth_score_none_when_no_signals() -> None:
    data = CompanyEnrichmentData(name="Acme")
    assert compute_growth_score(data) is None


def test_growth_score_higher_for_later_stage() -> None:
    seed = CompanyEnrichmentData(name="A", funding_stage="seed", company_size="11-50")
    series_c = CompanyEnrichmentData(name="B", funding_stage="series_c", company_size="201-500")
    assert compute_growth_score(seed) < compute_growth_score(series_c)


def test_growth_score_remote_policy_bumps_score() -> None:
    base = CompanyEnrichmentData(name="A", funding_stage="series_b", company_size="51-200")
    remote = CompanyEnrichmentData(
        name="A", funding_stage="series_b", company_size="51-200",
        remote_policy="remote_first",
    )
    assert compute_growth_score(remote) > compute_growth_score(base)


def test_risk_score_none_when_no_signals() -> None:
    data = CompanyEnrichmentData(name="Acme")
    assert compute_risk_score(data) is None


def test_risk_score_higher_for_early_stage_small_team() -> None:
    early = CompanyEnrichmentData(name="A", funding_stage="pre_seed", company_size="1-10")
    later = CompanyEnrichmentData(name="B", funding_stage="series_c", company_size="501-1000")
    assert compute_risk_score(early) > compute_risk_score(later)


def test_apply_recommendation_yes_when_growth_high_and_risk_low() -> None:
    assert compute_apply_recommendation(growth=80, risk=20) is True


def test_apply_recommendation_no_when_growth_low() -> None:
    assert compute_apply_recommendation(growth=30, risk=20) is False


def test_apply_recommendation_no_when_risk_high() -> None:
    assert compute_apply_recommendation(growth=80, risk=70) is False


def test_apply_recommendation_none_when_both_unknown() -> None:
    assert compute_apply_recommendation(growth=None, risk=None) is None


def test_render_summary_uses_only_known_fields() -> None:
    data = CompanyEnrichmentData(
        name="Acme",
        industry="fintech",
        company_size="51-200",
        funding_stage="series_b",
    )
    s = render_summary(data)
    assert "Acme" in s
    assert "fintech" in s
    assert "51-200" in s
    assert "series_b" in s


def test_render_summary_none_when_nothing_known() -> None:
    assert render_summary(CompanyEnrichmentData(name="Acme")) is None


def test_merge_enrichment_data_new_wins_but_doesnt_blank_old() -> None:
    old = CompanyEnrichmentData(name="A", industry="fintech", company_size="51-200")
    new = CompanyEnrichmentData(name="A", company_size="201-500", funding_stage="series_c")
    merged = merge_enrichment_data(old, new)
    assert merged.industry == "fintech"  # preserved
    assert merged.company_size == "201-500"  # overwritten
    assert merged.funding_stage == "series_c"  # added


# --------------------------- service --------------------------------------


class _StubProvider(EnrichmentProvider):
    name = "stub"

    def __init__(self, data: CompanyEnrichmentData) -> None:
        self._data = data
        self.calls = 0

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        self.calls += 1
        return self._data


async def test_service_enrich_persists_to_company_profiles() -> None:
    await _wipe("Acme")
    provider = _StubProvider(
        CompanyEnrichmentData(
            name="Acme",
            industry="fintech",
            company_size="51-200",
            funding_stage="series_b",
            remote_policy="remote_first",
        )
    )
    service = CompanyIntelligenceService(providers=[provider])
    snap = await service.enrich("Acme")
    assert snap.name == "Acme"
    assert snap.industry == "fintech"
    assert snap.growth_score is not None
    assert snap.summary and "Acme" in snap.summary
    assert provider.calls == 1


async def test_service_get_cached_returns_within_ttl() -> None:
    await _wipe("Acme")
    provider = _StubProvider(
        CompanyEnrichmentData(name="Acme", industry="fintech", company_size="51-200")
    )
    service = CompanyIntelligenceService(providers=[provider], ttl=timedelta(hours=1))
    await service.enrich("Acme")
    cached = await service.get_cached("Acme")
    assert cached is not None
    assert cached.name == "Acme"


async def test_service_get_cached_returns_none_after_ttl_expiry() -> None:
    await _wipe("Acme")
    provider = _StubProvider(
        CompanyEnrichmentData(name="Acme", industry="fintech")
    )
    service = CompanyIntelligenceService(providers=[provider], ttl=timedelta(seconds=1))
    await service.enrich("Acme")
    future = datetime.now(UTC) + timedelta(hours=24)
    cached = await service.get_cached("Acme", now=future)
    assert cached is None


async def test_service_get_or_enrich_uses_cache_when_fresh() -> None:
    await _wipe("Acme")
    provider = _StubProvider(
        CompanyEnrichmentData(name="Acme", industry="fintech", company_size="51-200")
    )
    service = CompanyIntelligenceService(providers=[provider], ttl=timedelta(hours=1))
    await service.get_or_enrich("Acme")
    assert provider.calls == 1
    await service.get_or_enrich("Acme")
    assert provider.calls == 1  # cache hit


async def test_service_with_no_provider_data_keeps_fields_null() -> None:
    await _wipe("UnknownCo")
    provider = _StubProvider(CompanyEnrichmentData(name="UnknownCo"))
    service = CompanyIntelligenceService(providers=[provider])
    snap = await service.enrich("UnknownCo")
    assert snap.industry is None
    assert snap.growth_score is None
    assert snap.risk_score is None
    assert snap.summary is None
    assert snap.apply_recommendation is None


async def test_service_provider_error_doesnt_break_service() -> None:
    await _wipe("BrokeCo")

    class _BrokenProvider(EnrichmentProvider):
        name = "broken"

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            raise RuntimeError("boom")

    good = _StubProvider(
        CompanyEnrichmentData(name="BrokeCo", industry="fintech", company_size="51-200")
    )
    service = CompanyIntelligenceService(providers=[_BrokenProvider(), good])
    snap = await service.enrich("BrokeCo")
    assert snap.industry == "fintech"  # the good provider still ran
