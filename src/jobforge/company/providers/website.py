"""CompanyWebsiteProvider — pulls hiring/team/tech signals off the company's own site.

Scope is intentionally narrow:
  - careers page → counts of open roles (hiring velocity)
  - homepage and `/about` → engineering-team and tech-stack hints

Failures (timeouts, 4xx, malformed HTML) yield empty data, never an exception
bubbling up. Tests inject a fake transport so no real network is touched.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from jobforge.company.base import (
    CompanyEnrichmentData,
    CompanySignal,
    EnrichmentProvider,
)
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.company.website")

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_TECH_KEYWORDS = {
    "python",
    "django",
    "fastapi",
    "rails",
    "ruby",
    "go",
    "golang",
    "rust",
    "java",
    "kotlin",
    "scala",
    "elixir",
    "typescript",
    "javascript",
    "node.js",
    "react",
    "vue",
    "angular",
    "svelte",
    "next.js",
    "postgres",
    "postgresql",
    "mysql",
    "redis",
    "kafka",
    "snowflake",
    "kubernetes",
    "terraform",
    "aws",
    "gcp",
    "azure",
    "graphql",
    "grpc",
}

# Heuristic open-role detection — we look for repeated occurrences of phrases
# that virtually all careers pages share.
_OPEN_ROLE_RE = re.compile(
    r"(?:<li[^>]*>|<a[^>]*href=\"[^\"]*(?:careers|jobs)/[^\"]+\")",
    re.IGNORECASE,
)

_CAREERS_PATHS = ("/careers", "/jobs", "/company/careers", "/about/careers")


def _normalize_website(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        return "https://" + value
    return value


def _extract_tech_stack(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for kw in _TECH_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            found.append(kw)
    return found[:30]


def _extract_open_role_count(text: str) -> int | None:
    matches = _OPEN_ROLE_RE.findall(text)
    if not matches:
        return None
    # Be conservative — only trust if we see at least 3 hits.
    if len(matches) < 3:
        return None
    return min(500, len(matches))


def _hiring_velocity(open_roles: int | None) -> int | None:
    if open_roles is None:
        return None
    # Smooth log-ish curve: 0 → 0, 5 → ~30, 25 → ~60, 100+ → ~90.
    if open_roles <= 1:
        return 5
    if open_roles >= 200:
        return 95
    # Piecewise to stay deterministic without importing math.
    if open_roles <= 5:
        return 15 + (open_roles - 1) * 4
    if open_roles <= 25:
        return 35 + (open_roles - 5) * 1
    if open_roles <= 100:
        return 60 + (open_roles - 25) // 5
    return 75 + (open_roles - 100) // 5


def _eng_team_signals(text: str) -> dict[str, Any]:
    lower = text.lower()
    signals: dict[str, Any] = {}
    if "engineering blog" in lower:
        signals["has_engineering_blog"] = True
    if "open source" in lower or "open-source" in lower:
        signals["mentions_open_source"] = True
    if "remote-first" in lower or "remote first" in lower:
        signals["remote_first_mention"] = True
    return signals


class CompanyWebsiteProvider(EnrichmentProvider):
    """Scrapes the company's own site for hiring + team signals.

    The provider is intentionally tolerant — every request is wrapped in a
    try/except and bad data just yields empty fields. The caller wires this
    into the same provider chain as the others and merges results.
    """

    name = "website"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _fetch(self, url: str) -> str | None:
        try:
            client = await self._get_client()
            response = await client.get(url)
            if response.status_code >= 400:
                return None
            return response.text
        except (httpx.HTTPError, OSError) as exc:
            log.info(
                "company.website.fetch_failed",
                extra={"url": url, "error": type(exc).__name__},
            )
            return None

    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        website = hints.website if hints else None
        if not website:
            return CompanyEnrichmentData(name=company_name)

        url = _normalize_website(website)
        parsed = urlparse(url)
        if not parsed.netloc:
            return CompanyEnrichmentData(name=company_name)

        home_text = await self._fetch(url)
        careers_text: str | None = None
        for path in _CAREERS_PATHS:
            careers_text = await self._fetch(urljoin(url, path))
            if careers_text:
                break

        combined = "\n".join(t for t in (home_text, careers_text) if t)
        if not combined:
            return CompanyEnrichmentData(name=company_name, website=url)

        tech = _extract_tech_stack(combined)
        open_roles = (
            _extract_open_role_count(careers_text) if careers_text else None
        )
        velocity = _hiring_velocity(open_roles)
        eng_signals = _eng_team_signals(combined)
        now = datetime.now(UTC)

        signals: list[CompanySignal] = []
        if open_roles is not None:
            signals.append(
                CompanySignal(
                    kind="hiring_velocity",
                    value=open_roles,
                    source=self.name,
                    confidence=65,
                    notes=f"{open_roles} open-role markers on careers page",
                    observed_at=now,
                )
            )
        if tech:
            signals.append(
                CompanySignal(
                    kind="tech_stack",
                    value=tech,
                    source=self.name,
                    confidence=55,
                    observed_at=now,
                )
            )
        if eng_signals:
            signals.append(
                CompanySignal(
                    kind="engineering_team",
                    value=eng_signals,
                    source=self.name,
                    confidence=50,
                    observed_at=now,
                )
            )

        return CompanyEnrichmentData(
            name=company_name,
            website=url,
            tech_stack=tech,
            open_roles_count=open_roles,
            hiring_velocity_score=velocity,
            engineering_team_signals=eng_signals,
            signals=signals,
        )
