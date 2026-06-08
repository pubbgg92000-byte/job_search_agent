"""Adapter registry — maps a JobSource row to a concrete adapter instance."""
from __future__ import annotations

from typing import Any

from jobforge.discovery.ashby import AshbyAdapter
from jobforge.discovery.base import JobSourceAdapter
from jobforge.discovery.greenhouse import GreenhouseAdapter
from jobforge.discovery.lever import LeverAdapter
from jobforge.discovery.remoteok import RemoteOKAdapter
from jobforge.discovery.remotive import RemotiveAdapter
from jobforge.discovery.wwr import DEFAULT_CATEGORY, WWRAdapter


def build_adapter(
    kind: str, slug: str | None, config: dict[str, Any] | None
) -> JobSourceAdapter:
    """Return an adapter instance for a (kind, slug, config) row from job_sources."""
    cfg = config or {}
    company_override = cfg.get("company")
    if kind == "greenhouse":
        if not slug:
            raise ValueError("greenhouse source requires a board slug")
        return GreenhouseAdapter(slug, company_override=company_override)
    if kind == "lever":
        if not slug:
            raise ValueError("lever source requires an org slug")
        return LeverAdapter(slug, company_override=company_override)
    if kind == "ashby":
        if not slug:
            raise ValueError("ashby source requires an org slug")
        return AshbyAdapter(slug, company_override=company_override)
    if kind == "remoteok":
        return RemoteOKAdapter()
    if kind == "remotive":
        return RemotiveAdapter()
    if kind == "wwr":
        return WWRAdapter(category=cfg.get("category", DEFAULT_CATEGORY))
    raise ValueError(f"unknown source kind: {kind}")


SUPPORTED_KINDS = ("greenhouse", "lever", "ashby", "remoteok", "remotive", "wwr")
