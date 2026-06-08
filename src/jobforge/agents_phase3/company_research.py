"""Company research agent — Phase 3B implementation.

`CompanyResearchAgent` (the ABC) lives here for backward compatibility; the
new `DeterministicResearchAgent` is a concrete implementation that fans out
across the Phase 3B providers (manual seed + website + structured web
research + news) and synthesizes a `CompanySnapshot`.

The agent honors the no-hallucination rule: providers that have no data
yield empty payloads, and unknown fields stay None all the way through to
the API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from jobforge.company.base import CompanySnapshot, EnrichmentProvider
from jobforge.company.providers.manual import ManualProvider
from jobforge.company.providers.news import NewsProvider
from jobforge.company.providers.web_research import WebResearchProvider
from jobforge.company.providers.website import CompanyWebsiteProvider
from jobforge.company.service import CompanyIntelligenceService


class CompanyResearchAgent(ABC):
    @abstractmethod
    async def research(self, company_name: str) -> CompanySnapshot:
        """Return a fully-populated snapshot for the named company.

        Implementations may call external APIs. They MUST honor the
        no-hallucination rule: unknown fields stay None.
        """


class DeterministicResearchAgent(CompanyResearchAgent):
    """A research agent backed by the Phase 3B provider stack.

    Composition order matters: ManualProvider runs first so admin-seeded
    overrides win on conflict. The site provider runs second so it can use
    the website URL the manual seed (or any earlier provider) supplied.
    Web research and news round it out — they're the most likely to fail
    (external APIs), and that failure is non-fatal because the intelligence
    service catches per-provider exceptions.

    The agent is intentionally thin — every behavior lives in providers +
    the intelligence service. The agent just composes them.
    """

    def __init__(
        self,
        providers: list[EnrichmentProvider] | None = None,
        service: CompanyIntelligenceService | None = None,
    ) -> None:
        if providers is None:
            providers = [
                ManualProvider(),
                CompanyWebsiteProvider(),
                WebResearchProvider(),
                NewsProvider(),
            ]
        self._service = service or CompanyIntelligenceService(providers=providers)

    @property
    def service(self) -> CompanyIntelligenceService:
        return self._service

    async def research(self, company_name: str) -> CompanySnapshot:
        return await self._service.get_or_enrich(company_name)

    async def aclose(self) -> None:
        """Shut down any owned httpx clients on the providers we created."""
        for provider in self._service.providers:
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                await aclose()
