"""Base interface for outreach discovery providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class DiscoveredContact:
    """A candidate contact returned by a discovery provider.

    Confidence is a 0-100 hint to the service layer; we never auto-send
    to anyone below 40 from a non-manual source.
    """

    name: str
    kind: str = "recruiter"
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str = "manual"
    confidence: int = 50
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ContactDiscoveryProvider(Protocol):
    """All providers MUST be safe to call with no network configured."""

    name: str

    async def discover(
        self, company: str, hints: dict[str, Any] | None = None
    ) -> list[DiscoveredContact]: ...
