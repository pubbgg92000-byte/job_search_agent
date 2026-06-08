"""Web-research provider — disabled unless `OUTREACH_RESEARCH_ENDPOINT` is set.

The actual HTTP shape matches the Phase 3B company research provider:
POST {endpoint} with `{"company": ..., "kinds": [...]}` and expect back
`{"contacts": [{name, role, kind, linkedin_url, email, source}, ...]}`.

When the endpoint is not configured we return [] — the rest of the service
keeps working with whatever the manual provider supplied.
"""
from __future__ import annotations

from typing import Any

import httpx

from jobforge.config import get_settings
from jobforge.logging_setup import get_logger
from jobforge.outreach.providers.base import DiscoveredContact

log = get_logger("jobforge.outreach.web_research")

_DEFAULT_KINDS = ("recruiter", "talent_partner", "hiring_manager")


class WebResearchProvider:
    name = "web_research"

    def __init__(self, http: httpx.AsyncClient | None = None, timeout: float = 15.0) -> None:
        self._http = http
        self._timeout = timeout

    def _endpoint(self) -> str | None:
        settings = get_settings()
        return getattr(settings, "outreach_research_endpoint", None)

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self._http is not None:
            resp = await self._http.post(url, json=payload, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            log.warning(
                "outreach.research.http_error",
                extra={"status": resp.status_code, "url": url},
            )
            return None
        try:
            return resp.json()
        except Exception:
            log.warning("outreach.research.bad_json")
            return None

    async def discover(
        self, company: str, hints: dict[str, Any] | None = None
    ) -> list[DiscoveredContact]:
        url = self._endpoint()
        if not url:
            return []
        payload: dict[str, Any] = {"company": company, "kinds": list(_DEFAULT_KINDS)}
        if hints:
            payload["hints"] = dict(hints)
        data = await self._post(url, payload)
        if not isinstance(data, dict):
            return []
        items = data.get("contacts") or []
        out: list[DiscoveredContact] = []
        for it in items:
            if not isinstance(it, dict) or not it.get("name"):
                continue
            out.append(
                DiscoveredContact(
                    name=str(it["name"]),
                    kind=str(it.get("kind") or "recruiter"),
                    role=it.get("role"),
                    linkedin_url=it.get("linkedin_url"),
                    email=it.get("email"),
                    phone=it.get("phone"),
                    source="web_research",
                    confidence=int(it.get("confidence") or 60),
                    notes=it.get("notes"),
                    extra=it.get("extra") or {},
                )
            )
        return out
