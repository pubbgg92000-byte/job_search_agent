"""Phase 3B tests — providers, scoring extensions, research agent, caching."""
from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import delete

from jobforge.agents_phase3.company_research import DeterministicResearchAgent
from jobforge.company import (
    CompanyEnrichmentData,
    CompanyIntelligenceService,
    CompanySignal,
    EnrichmentProvider,
    compute_confidence_score,
    compute_growth_score,
    compute_risk_score,
)
from jobforge.company.providers.news import NewsProvider, _classify, _parse_item
from jobforge.company.providers.web_research import (
    WebResearchProvider,
    _validate_funding,
    _validate_remote,
    _validate_size,
)
from jobforge.company.providers.website import (
    CompanyWebsiteProvider,
    _extract_open_role_count,
    _extract_tech_stack,
    _hiring_velocity,
    _normalize_website,
)
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope


async def _wipe(name: str) -> None:
    async with session_scope() as session:
        await session.execute(delete(CompanyProfile).where(CompanyProfile.name == name))


def _make_mock_client(handler) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by an in-process handler.

    No network — `httpx.MockTransport` calls `handler(request)` synchronously
    for every request the provider makes.
    """
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, follow_redirects=True)


# --------------------------- scoring extensions ----------------------------


def test_confidence_score_none_without_signals() -> None:
    data = CompanyEnrichmentData(name="Acme")
    assert compute_confidence_score(data) is None


def test_confidence_score_rises_with_distinct_signal_kinds() -> None:
    base = CompanyEnrichmentData(
        name="A",
        signals=[
            CompanySignal(kind="funding", value="series_b", source="x", confidence=60)
        ],
    )
    broad = CompanyEnrichmentData(
        name="A",
        signals=[
            CompanySignal(kind="funding", value="series_b", source="x", confidence=60),
            CompanySignal(kind="headcount", value="51-200", source="x", confidence=60),
            CompanySignal(kind="tech_stack", value=["python"], source="x", confidence=60),
        ],
    )
    assert compute_confidence_score(broad) > compute_confidence_score(base)


def test_confidence_score_clamped_to_100() -> None:
    data = CompanyEnrichmentData(
        name="A",
        signals=[
            CompanySignal(kind="funding", value="x", source="x", confidence=100),
            CompanySignal(kind="headcount", value="x", source="x", confidence=100),
            CompanySignal(kind="industry", value="x", source="x", confidence=100),
            CompanySignal(kind="news", value="x", source="x", confidence=100),
            CompanySignal(kind="growth", value="x", source="x", confidence=100),
        ],
    )
    assert compute_confidence_score(data) <= 100


def test_growth_score_incorporates_hiring_velocity() -> None:
    base = CompanyEnrichmentData(
        name="A", funding_stage="series_b", company_size="51-200"
    )
    fast_hiring = CompanyEnrichmentData(
        name="A",
        funding_stage="series_b",
        company_size="51-200",
        hiring_velocity_score=90,
    )
    assert compute_growth_score(fast_hiring) > compute_growth_score(base)


def test_growth_score_penalised_by_layoffs() -> None:
    healthy = CompanyEnrichmentData(
        name="A", funding_stage="series_b", company_size="51-200"
    )
    layoffs = CompanyEnrichmentData(
        name="A",
        funding_stage="series_b",
        company_size="51-200",
        layoffs_detected=True,
    )
    assert compute_growth_score(layoffs) < compute_growth_score(healthy)


def test_risk_score_uplifted_by_layoffs_alone() -> None:
    only_layoffs = CompanyEnrichmentData(name="A", layoffs_detected=True)
    risk = compute_risk_score(only_layoffs)
    assert risk is not None and risk >= 40


def test_risk_score_remains_none_when_only_zero_velocity_present() -> None:
    data = CompanyEnrichmentData(name="A", hiring_velocity_score=5)
    assert compute_risk_score(data) is None


# --------------------------- website provider ------------------------------


def test_website_normalize_adds_https() -> None:
    assert _normalize_website("acme.test").startswith("https://")
    assert _normalize_website("http://acme.test") == "http://acme.test"


def test_website_extract_tech_stack_finds_known_keywords() -> None:
    html = (
        "<html><body>We use Python, FastAPI, PostgreSQL, Rust and Kubernetes.</body></html>"
    )
    found = _extract_tech_stack(html)
    assert "python" in found
    assert "fastapi" in found
    assert "postgresql" in found
    assert "rust" in found
    assert "kubernetes" in found


def test_website_extract_open_role_count_requires_threshold() -> None:
    too_few = "<li>One</li><li>Two</li>"
    assert _extract_open_role_count(too_few) is None
    plenty = (
        "<li>A</li><li>B</li><li>C</li>"
        '<a href="https://example.com/careers/eng">Eng</a>'
    )
    assert _extract_open_role_count(plenty) is not None


def test_website_hiring_velocity_monotonic() -> None:
    assert _hiring_velocity(None) is None
    assert _hiring_velocity(1) is not None
    assert (_hiring_velocity(5) or 0) < (_hiring_velocity(30) or 0)
    assert (_hiring_velocity(30) or 0) < (_hiring_velocity(200) or 0)


async def test_website_provider_returns_empty_without_website_hint() -> None:
    provider = CompanyWebsiteProvider(client=_make_mock_client(lambda req: httpx.Response(200, text="")))
    data = await provider.enrich("Acme")
    assert data.tech_stack == []
    assert data.hiring_velocity_score is None


async def test_website_provider_parses_careers_page() -> None:
    careers_html = (
        "<html><body>"
        + "<li>Job A</li><li>Job B</li><li>Job C</li><li>Job D</li>"
        + "<a href='/careers/python-engineer'>Python Engineer</a>"
        + "We use Python, Rust, PostgreSQL. Our engineering blog publishes weekly."
        + "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "/careers" in str(request.url):
            return httpx.Response(200, text=careers_html)
        return httpx.Response(200, text=careers_html)

    provider = CompanyWebsiteProvider(client=_make_mock_client(handler))
    data = await provider.enrich(
        "Acme",
        hints=CompanyEnrichmentData(name="Acme", website="https://acme.test"),
    )
    assert data.open_roles_count is not None
    assert data.hiring_velocity_score is not None
    assert "python" in data.tech_stack
    assert data.engineering_team_signals.get("has_engineering_blog") is True
    assert any(s.kind == "hiring_velocity" for s in data.signals)


async def test_website_provider_tolerates_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = CompanyWebsiteProvider(client=_make_mock_client(handler))
    data = await provider.enrich(
        "Acme",
        hints=CompanyEnrichmentData(name="Acme", website="https://acme.test"),
    )
    assert data.is_empty() or data.website == "https://acme.test"


# --------------------------- web research provider -------------------------


def test_web_research_validators() -> None:
    assert _validate_funding("Series B") == "series_b"
    assert _validate_funding("not a stage") is None
    assert _validate_funding(123) is None
    assert _validate_size("51-200") == "51-200"
    assert _validate_size("infinite") is None
    assert _validate_remote("Remote First") == "remote_first"
    assert _validate_remote("never heard of it") is None


async def test_web_research_disabled_without_endpoint() -> None:
    provider = WebResearchProvider(
        client=_make_mock_client(lambda req: httpx.Response(500)),
        endpoint=None,
    )
    data = await provider.enrich("Acme")
    assert data.is_empty()


async def test_web_research_parses_funding_and_signals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "funding_stage": "series_c",
                "company_size": "201-500",
                "industry": "fintech",
                "remote_policy": "remote_first",
                "tech_stack": ["Python", "Rust", "Kubernetes"],
                "glassdoor": {"rating": 4.2, "ceo_approval": 80},
                "confidence": 75,
            },
        )

    provider = WebResearchProvider(
        client=_make_mock_client(handler),
        endpoint="https://example.test/lookup?q={name}",
    )
    data = await provider.enrich("Acme")
    assert data.funding_stage == "series_c"
    assert data.company_size == "201-500"
    assert data.industry == "fintech"
    assert data.remote_policy == "remote_first"
    assert "python" in data.tech_stack
    assert data.glassdoor_signals["rating"] == 4.2
    kinds = {s.kind for s in data.signals}
    assert {"funding", "headcount", "industry", "remote_policy"}.issubset(kinds)


async def test_web_research_rejects_unknown_funding_stage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"funding_stage": "made-up-stage", "company_size": "Infinite"}
        )

    provider = WebResearchProvider(
        client=_make_mock_client(handler), endpoint="https://example.test/q?company={name}"
    )
    data = await provider.enrich("Acme")
    assert data.funding_stage is None
    assert data.company_size is None


async def test_web_research_handles_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = WebResearchProvider(
        client=_make_mock_client(handler), endpoint="https://example.test/x"
    )
    data = await provider.enrich("Acme")
    assert data.is_empty()


async def test_web_research_handles_malformed_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})

    provider = WebResearchProvider(
        client=_make_mock_client(handler), endpoint="https://example.test/x"
    )
    data = await provider.enrich("Acme")
    assert data.is_empty()


async def test_web_research_builds_url_with_name_template() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    provider = WebResearchProvider(
        client=_make_mock_client(handler),
        endpoint="https://example.test/lookup?q={name}",
    )
    await provider.enrich("Acme Co")
    assert "Acme%20Co" in seen["url"]


# --------------------------- news provider ---------------------------------


def test_news_classifier_buckets_correctly() -> None:
    assert _classify("Acme raises $50M", "") == "funding"
    assert _classify("Acme announces layoffs", "") == "layoffs"
    assert _classify("Acme expands to Asia", "") == "growth"
    assert _classify("Acme: an interview", "") == "news"


def test_news_parse_rejects_non_dict() -> None:
    assert _parse_item("nope") is None
    assert _parse_item({"title": ""}) is None
    item = _parse_item(
        {"title": "Acme raises 100M", "summary": "Series B led by ..."}
    )
    assert item is not None
    assert item["category"] == "funding"


async def test_news_disabled_without_endpoint() -> None:
    provider = NewsProvider(
        client=_make_mock_client(lambda req: httpx.Response(500))
    )
    data = await provider.enrich("Acme")
    assert data.is_empty()


async def test_news_provider_detects_layoffs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"title": "Acme announces layoffs", "summary": "cuts 15% of workforce"},
                {"title": "Acme expands product", "summary": "ships new feature"},
            ],
        )

    provider = NewsProvider(
        client=_make_mock_client(handler), endpoint="https://news.test/feed?company={name}"
    )
    data = await provider.enrich("Acme")
    assert data.layoffs_detected is True
    assert len(data.news_items) == 2
    assert any(s.kind == "layoffs" for s in data.signals)


async def test_news_provider_handles_dict_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"items": [{"title": "Acme raises $20M", "summary": ""}]}
        )

    provider = NewsProvider(
        client=_make_mock_client(handler), endpoint="https://news.test/feed"
    )
    data = await provider.enrich("Acme")
    assert len(data.news_items) == 1
    assert data.news_items[0]["category"] == "funding"


async def test_news_provider_skips_malformed_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"title": "Acme grows"},
                "garbage",
                {"missing_title": True},
            ],
        )

    provider = NewsProvider(
        client=_make_mock_client(handler), endpoint="https://news.test/x"
    )
    data = await provider.enrich("Acme")
    assert len(data.news_items) == 1


# --------------------------- service + caching -----------------------------


class _NoOpProvider(EnrichmentProvider):
    """Helper that records hints it was given without doing any work."""

    name = "noop"

    def __init__(self) -> None:
        self.calls = 0
        self.last_hints: CompanyEnrichmentData | None = None

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        self.calls += 1
        self.last_hints = hints
        return CompanyEnrichmentData(name=company_name)


async def test_service_passes_accumulated_hints_to_next_provider() -> None:
    await _wipe("HintCo")

    class _FundingProvider(EnrichmentProvider):
        name = "funding"

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            return CompanyEnrichmentData(
                name=company_name, website="https://hintco.test", industry="fintech"
            )

    observer = _NoOpProvider()
    service = CompanyIntelligenceService(providers=[_FundingProvider(), observer])
    await service.enrich("HintCo")
    assert observer.last_hints is not None
    assert observer.last_hints.website == "https://hintco.test"


async def test_service_default_ttl_is_seven_days() -> None:
    assert CompanyIntelligenceService().ttl == timedelta(days=7)


async def test_service_persists_phase3b_fields_to_snapshot() -> None:
    await _wipe("Phase3BCo")

    class _Stub(EnrichmentProvider):
        name = "stub"

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            return CompanyEnrichmentData(
                name=company_name,
                industry="fintech",
                company_size="51-200",
                funding_stage="series_b",
                hiring_velocity_score=70,
                open_roles_count=18,
                tech_stack=["python", "rust"],
                layoffs_detected=False,
                news_items=[{"title": "Hello", "summary": "", "url": None, "published_at": None, "category": "news"}],
                signals=[
                    CompanySignal(kind="funding", value="series_b", source="stub", confidence=70)
                ],
            )

    service = CompanyIntelligenceService(providers=[_Stub()])
    snap = await service.enrich("Phase3BCo")
    assert snap.confidence_score is not None
    assert snap.hiring_velocity_score == 70
    assert snap.open_roles_count == 18
    assert "python" in snap.tech_stack
    assert len(snap.news_items) == 1
    assert len(snap.signals) == 1


async def test_service_round_trip_through_db_preserves_phase3b() -> None:
    await _wipe("RoundTripCo")

    class _Stub(EnrichmentProvider):
        name = "stub"

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            return CompanyEnrichmentData(
                name=company_name,
                industry="fintech",
                tech_stack=["go", "kafka"],
                hiring_velocity_score=42,
                signals=[
                    CompanySignal(kind="tech_stack", value=["go"], source="stub", confidence=55)
                ],
            )

    service = CompanyIntelligenceService(providers=[_Stub()])
    await service.enrich("RoundTripCo")
    cached = await service.get_cached("RoundTripCo")
    assert cached is not None
    assert cached.hiring_velocity_score == 42
    assert "go" in cached.tech_stack
    assert len(cached.signals) == 1


# --------------------------- research agent --------------------------------


async def test_research_agent_uses_provider_stack_and_caches() -> None:
    await _wipe("AgentCo")

    class _Stub(EnrichmentProvider):
        name = "stub"

        def __init__(self) -> None:
            self.calls = 0

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            self.calls += 1
            return CompanyEnrichmentData(
                name=company_name, industry="fintech", company_size="51-200"
            )

    stub = _Stub()
    agent = DeterministicResearchAgent(providers=[stub])
    snap = await agent.research("AgentCo")
    assert snap.industry == "fintech"
    # second call should hit cache, not re-invoke
    await agent.research("AgentCo")
    assert stub.calls == 1


async def test_research_agent_never_hallucinates_when_all_providers_empty() -> None:
    await _wipe("BlankCo")

    class _Empty(EnrichmentProvider):
        name = "empty"

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            return CompanyEnrichmentData(name=company_name)

    agent = DeterministicResearchAgent(providers=[_Empty()])
    snap = await agent.research("BlankCo")
    assert snap.industry is None
    assert snap.growth_score is None
    assert snap.risk_score is None
    assert snap.confidence_score is None
    assert snap.tech_stack == ()


async def test_research_agent_default_stack_has_four_providers() -> None:
    agent = DeterministicResearchAgent()
    names = [p.name for p in agent.service.providers]
    assert names == ["manual", "website", "web_research", "news"]
    await agent.aclose()
