"""Outreach discovery providers.

A provider takes `(company_name, hints)` and returns a list of
:class:`DiscoveredContact`. Providers are pure with respect to the database
— the service layer is the only place we insert rows. This lets us run
several providers in series and dedupe the union before write.

The default `web_research` provider only does network I/O when an explicit
endpoint is configured; otherwise it returns []. In tests the providers
are always mocked.
"""
from __future__ import annotations

from jobforge.outreach.providers.base import (
    ContactDiscoveryProvider,
    DiscoveredContact,
)
from jobforge.outreach.providers.manual import ManualProvider
from jobforge.outreach.providers.web_research import WebResearchProvider

__all__ = [
    "ContactDiscoveryProvider",
    "DiscoveredContact",
    "ManualProvider",
    "WebResearchProvider",
]
