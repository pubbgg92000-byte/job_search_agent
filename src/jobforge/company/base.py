"""Shared types for company intelligence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

SignalKind = Literal[
    "funding",
    "headcount",
    "industry",
    "remote_policy",
    "hiring_velocity",
    "growth",
    "layoffs",
    "engineering_team",
    "tech_stack",
    "glassdoor",
    "news",
]


@dataclass(frozen=True)
class CompanySignal:
    """A single piece of evidence about a company, with provenance.

    Providers emit signals so the agent can render an audit trail and the
    confidence score can weight by source quality.
    """

    kind: SignalKind
    value: Any
    source: str
    confidence: int = 50  # 0-100; how much we trust this signal
    notes: str | None = None
    observed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "notes": self.notes,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
        }


@dataclass
class CompanyEnrichmentData:
    """Raw signals returned by a provider — every field is optional.

    Phase 2B fields drive the existing deterministic scoring. Phase 3B
    additions ride alongside in `signals` plus a few convenience aggregates.
    """

    name: str
    # Phase 2B fields (still drive growth/risk scoring)
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    funding_stage: str | None = None
    remote_policy: str | None = None
    raw_signals: dict[str, Any] = field(default_factory=dict)

    # Phase 3B additions
    signals: list[CompanySignal] = field(default_factory=list)
    hiring_velocity_score: int | None = None  # 0-100
    open_roles_count: int | None = None
    tech_stack: list[str] = field(default_factory=list)
    engineering_team_signals: dict[str, Any] = field(default_factory=dict)
    glassdoor_signals: dict[str, Any] = field(default_factory=dict)
    news_items: list[dict[str, Any]] = field(default_factory=list)
    layoffs_detected: bool | None = None

    def is_empty(self) -> bool:
        """True if no actual data was returned (just the company name)."""
        return all(
            v is None
            for v in (
                self.website,
                self.industry,
                self.company_size,
                self.funding_stage,
                self.remote_policy,
                self.hiring_velocity_score,
                self.open_roles_count,
                self.layoffs_detected,
            )
        ) and not (
            self.raw_signals
            or self.signals
            or self.tech_stack
            or self.engineering_team_signals
            or self.glassdoor_signals
            or self.news_items
        )


@dataclass(frozen=True)
class CompanySnapshot:
    """User-facing intelligence payload.

    Phase 2B fields stay; Phase 3B fields are additive — nothing is removed
    or renamed so existing API consumers keep working unchanged.
    """

    name: str
    website: str | None
    industry: str | None
    company_size: str | None
    funding_stage: str | None
    remote_policy: str | None
    growth_score: int | None
    risk_score: int | None
    summary: str | None
    apply_recommendation: bool | None
    last_updated_at: datetime
    # Phase 3B additions — additive
    confidence_score: int | None = None
    hiring_velocity_score: int | None = None
    open_roles_count: int | None = None
    tech_stack: tuple[str, ...] = ()
    layoffs_detected: bool | None = None
    news_items: tuple[dict[str, Any], ...] = ()
    engineering_team_signals: dict[str, Any] | None = None
    glassdoor_signals: dict[str, Any] | None = None
    signals: tuple[dict[str, Any], ...] = ()


class EnrichmentProvider(ABC):
    """One source of company data. Implementations may hit external APIs.

    Phase 3B added an optional `hints` argument so downstream providers can
    see what earlier providers learned (e.g. WebsiteProvider can use a
    website URL that ManualProvider seeded). Providers that don't care just
    accept and ignore the kwarg — old call sites without hints keep working.
    """

    name: str

    @abstractmethod
    async def enrich(
        self,
        company_name: str,
        *,
        hints: CompanyEnrichmentData | None = None,
    ) -> CompanyEnrichmentData:
        """Return whatever signals are available. Empty data is allowed."""


def _coalesce_int(*values: int | None) -> int | None:
    return next((v for v in values if v is not None), None)


def _coalesce_bool(*values: bool | None) -> bool | None:
    return next((v for v in values if v is not None), None)


def merge_enrichment_data(
    existing: CompanyEnrichmentData, new: CompanyEnrichmentData
) -> CompanyEnrichmentData:
    """Merge two enrichment payloads.

    Rules: never overwrite a known value with None. Collections (signals,
    news, tech stack) are unioned. Numeric Phase 3B scores prefer new when
    set; otherwise keep existing.
    """
    merged_raw = {**existing.raw_signals, **new.raw_signals}
    merged_tech = list(dict.fromkeys([*existing.tech_stack, *new.tech_stack]))
    merged_news = [*existing.news_items, *new.news_items]
    merged_signals = [*existing.signals, *new.signals]
    return CompanyEnrichmentData(
        name=new.name or existing.name,
        website=new.website or existing.website,
        industry=new.industry or existing.industry,
        company_size=new.company_size or existing.company_size,
        funding_stage=new.funding_stage or existing.funding_stage,
        remote_policy=new.remote_policy or existing.remote_policy,
        raw_signals=merged_raw,
        signals=merged_signals,
        hiring_velocity_score=_coalesce_int(
            new.hiring_velocity_score, existing.hiring_velocity_score
        ),
        open_roles_count=_coalesce_int(new.open_roles_count, existing.open_roles_count),
        tech_stack=merged_tech,
        engineering_team_signals={
            **existing.engineering_team_signals,
            **new.engineering_team_signals,
        },
        glassdoor_signals={**existing.glassdoor_signals, **new.glassdoor_signals},
        news_items=merged_news,
        layoffs_detected=_coalesce_bool(new.layoffs_detected, existing.layoffs_detected),
    )
