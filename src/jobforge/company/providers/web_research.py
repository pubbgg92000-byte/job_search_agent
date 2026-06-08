"""WebResearchProvider — pulls structured public-data signals.

This provider talks to a configurable JSON endpoint that returns a
deterministic, ranked list of facts about a company (funding stage,
headcount band, industry, glassdoor signals). Real deployments point this
at a commercial data API; the contract is intentionally small so any
adapter can satisfy it.

The provider must NEVER fabricate values. If the endpoint returns nothing —
or returns it in an unexpected shape — we yield an empty payload.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from jobforge.company.base import (
    CompanyEnrichmentData,
    CompanySignal,
    EnrichmentProvider,
)
from jobforge.config import get_settings
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.company.web_research")

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


_KNOWN_FUNDING_STAGES = {
    "bootstrapped",
    "pre_seed",
    "preseed",
    "seed",
    "series_a",
    "series_b",
    "series_c",
    "series_d",
    "series_e",
    "series_e_plus",
    "growth",
    "late_stage",
    "public",
    "ipo",
    "acquired",
}

_KNOWN_SIZE_BUCKETS = {
    "1-10",
    "11-50",
    "51-200",
    "201-500",
    "501-1000",
    "1001-5000",
    "5000+",
}

_REMOTE_POLICIES = {
    "remote",
    "remote_first",
    "remote-first",
    "hybrid",
    "office",
    "office_first",
}


def _safe_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _validate_funding(value: Any) -> str | None:
    s = _safe_str(value)
    if not s:
        return None
    canonical = s.lower().replace(" ", "_")
    return canonical if canonical in _KNOWN_FUNDING_STAGES else None


def _validate_size(value: Any) -> str | None:
    s = _safe_str(value)
    return s if s in _KNOWN_SIZE_BUCKETS else None


def _validate_remote(value: Any) -> str | None:
    s = _safe_str(value)
    if not s:
        return None
    canonical = s.lower().replace(" ", "_")
    return canonical if canonical in _REMOTE_POLICIES else None


class WebResearchProvider(EnrichmentProvider):
    """Aggregates structured public-data lookups.

    Configure via env: `COMPANY_RESEARCH_ENDPOINT` (a URL templating the
    company name with `{name}` or `?company=`). If unset, the provider
    returns empty data without making any request.
    """

    name = "web_research"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        endpoint: str | None = None,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._endpoint = endpoint
        self._timeout = timeout

    def _resolve_endpoint(self) -> str | None:
        if self._endpoint:
            return self._endpoint
        cfg_endpoint = getattr(get_settings(), "company_research_endpoint", None)
        return cfg_endpoint or None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_url(self, endpoint: str, company_name: str) -> str:
        encoded = quote(company_name)
        if "{name}" in endpoint:
            return endpoint.replace("{name}", encoded)
        sep = "&" if "?" in endpoint else "?"
        return f"{endpoint}{sep}company={encoded}"

    async def _query(self, company_name: str) -> dict[str, Any] | None:
        endpoint = self._resolve_endpoint()
        if not endpoint:
            return None
        url = self._build_url(endpoint, company_name)
        try:
            client = await self._get_client()
            response = await client.get(url)
            if response.status_code != 200:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            log.info(
                "company.web_research.fetch_failed",
                extra={"company": company_name, "error": type(exc).__name__},
            )
            return None
        return payload if isinstance(payload, dict) else None

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        payload = await self._query(company_name)
        if not payload:
            return CompanyEnrichmentData(name=company_name)

        funding = _validate_funding(payload.get("funding_stage"))
        size = _validate_size(payload.get("company_size"))
        industry = _safe_str(payload.get("industry"))
        remote = _validate_remote(payload.get("remote_policy"))
        website = _safe_str(payload.get("website"))
        tech_stack_raw = payload.get("tech_stack") or []
        tech_stack = [
            t.lower()
            for t in tech_stack_raw
            if isinstance(t, str) and t.strip()
        ]
        glassdoor = payload.get("glassdoor") or {}
        if not isinstance(glassdoor, dict):
            glassdoor = {}
        confidence_raw = payload.get("confidence")
        provider_confidence = (
            int(confidence_raw)
            if isinstance(confidence_raw, (int, float)) and 0 <= confidence_raw <= 100
            else 60
        )

        now = datetime.now(UTC)
        signals: list[CompanySignal] = []
        if funding:
            signals.append(
                CompanySignal(
                    kind="funding",
                    value=funding,
                    source=self.name,
                    confidence=provider_confidence,
                    observed_at=now,
                )
            )
        if size:
            signals.append(
                CompanySignal(
                    kind="headcount",
                    value=size,
                    source=self.name,
                    confidence=provider_confidence,
                    observed_at=now,
                )
            )
        if industry:
            signals.append(
                CompanySignal(
                    kind="industry",
                    value=industry,
                    source=self.name,
                    confidence=provider_confidence,
                    observed_at=now,
                )
            )
        if remote:
            signals.append(
                CompanySignal(
                    kind="remote_policy",
                    value=remote,
                    source=self.name,
                    confidence=provider_confidence,
                    observed_at=now,
                )
            )
        if tech_stack:
            signals.append(
                CompanySignal(
                    kind="tech_stack",
                    value=tech_stack,
                    source=self.name,
                    confidence=provider_confidence,
                    observed_at=now,
                )
            )
        if glassdoor:
            signals.append(
                CompanySignal(
                    kind="glassdoor",
                    value=glassdoor,
                    source=self.name,
                    confidence=max(40, provider_confidence - 10),
                    observed_at=now,
                )
            )

        return CompanyEnrichmentData(
            name=company_name,
            website=website,
            industry=industry,
            company_size=size,
            funding_stage=funding,
            remote_policy=remote,
            tech_stack=tech_stack,
            glassdoor_signals=glassdoor,
            signals=signals,
        )
