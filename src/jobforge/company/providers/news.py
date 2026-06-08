"""NewsProvider — fetches recent press / blog hits and classifies them.

Talks to a configurable JSON endpoint that returns a list of recent news
items for a company. Each item is bucketed into a category (funding,
growth, layoffs, generic) by a small keyword classifier. Unknown items are
kept but tagged "news" without further interpretation.

The classifier is purely deterministic — no LLM — so identical inputs
always produce identical outputs.
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

log = get_logger("jobforge.company.news")

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_LAYOFF_KEYWORDS = ("layoff", "layoffs", "let go", "headcount cut", "workforce reduction")
_FUNDING_KEYWORDS = ("raises", "raised", "series ", "funding round", "ipo", "acquired")
_GROWTH_KEYWORDS = ("hires", "expands", "launches", "milestone", "doubles", "grows")


def _classify(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()
    if any(kw in blob for kw in _LAYOFF_KEYWORDS):
        return "layoffs"
    if any(kw in blob for kw in _FUNDING_KEYWORDS):
        return "funding"
    if any(kw in blob for kw in _GROWTH_KEYWORDS):
        return "growth"
    return "news"


def _parse_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    summary = raw.get("summary") if isinstance(raw.get("summary"), str) else ""
    url = raw.get("url") if isinstance(raw.get("url"), str) else None
    published_at = (
        raw.get("published_at") if isinstance(raw.get("published_at"), str) else None
    )
    category = _classify(title, summary or "")
    return {
        "title": title.strip(),
        "summary": (summary or "").strip(),
        "url": url,
        "published_at": published_at,
        "category": category,
    }


class NewsProvider(EnrichmentProvider):
    """Fetches and classifies recent company news.

    Configure via env: `COMPANY_NEWS_ENDPOINT`. Unset → no-op provider.
    """

    name = "news"

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
        return getattr(get_settings(), "company_news_endpoint", None) or None

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

    async def _query(self, company_name: str) -> list[Any]:
        endpoint = self._resolve_endpoint()
        if not endpoint:
            return []
        url = self._build_url(endpoint, company_name)
        try:
            client = await self._get_client()
            response = await client.get(url)
            if response.status_code != 200:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            log.info(
                "company.news.fetch_failed",
                extra={"company": company_name, "error": type(exc).__name__},
            )
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload["items"]
        return []

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        raw_items = await self._query(company_name)
        if not raw_items:
            return CompanyEnrichmentData(name=company_name)

        items = [parsed for parsed in (_parse_item(r) for r in raw_items) if parsed]
        if not items:
            return CompanyEnrichmentData(name=company_name)

        now = datetime.now(UTC)
        layoffs_detected = any(it["category"] == "layoffs" for it in items)
        signals: list[CompanySignal] = [
            CompanySignal(
                kind="news",
                value={"category": it["category"], "title": it["title"]},
                source=self.name,
                confidence=55,
                notes=it["url"],
                observed_at=now,
            )
            for it in items
        ]
        if layoffs_detected:
            signals.append(
                CompanySignal(
                    kind="layoffs",
                    value=True,
                    source=self.name,
                    confidence=70,
                    observed_at=now,
                )
            )

        return CompanyEnrichmentData(
            name=company_name,
            news_items=items,
            layoffs_detected=layoffs_detected if layoffs_detected else None,
            signals=signals,
        )
