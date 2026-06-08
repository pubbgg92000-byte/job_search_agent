"""Manual provider — echoes user-supplied seeds.

Used by the admin/seed flow (PUT /outreach/contacts) so the rest of the
service layer treats the same code path as auto-discovery.
"""
from __future__ import annotations

from typing import Any

from jobforge.outreach.providers.base import DiscoveredContact


class ManualProvider:
    name = "manual"

    def __init__(self, seeds: list[DiscoveredContact] | None = None) -> None:
        self._seeds = list(seeds or [])

    async def discover(
        self, company: str, hints: dict[str, Any] | None = None
    ) -> list[DiscoveredContact]:
        # Manual seeds are global to the provider instance — we don't filter
        # by company because callers seed per-company already.
        return [
            DiscoveredContact(
                name=s.name,
                kind=s.kind,
                role=s.role,
                linkedin_url=s.linkedin_url,
                email=s.email,
                phone=s.phone,
                source="manual",
                confidence=max(s.confidence, 75),
                notes=s.notes,
                extra=dict(s.extra),
            )
            for s in self._seeds
        ]
