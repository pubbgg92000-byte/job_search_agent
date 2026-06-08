"""Common types for the discovery layer."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RawJob:
    """A single normalized job listing.

    `source` and `source_job_id` together must be globally unique — they're the
    natural key we dedupe on.
    """

    source: str
    source_job_id: str
    company: str
    title: str
    location: str | None
    remote: bool
    description: str
    url: str
    posted_at: datetime | None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None


class JobSourceAdapter(ABC):
    """Abstract source adapter. One instance per configured source."""

    #: short identifier persisted in `discovered_jobs.source`.
    source: str

    @abstractmethod
    async def fetch_jobs(self) -> list[RawJob]:
        """Fetch and return all currently-listed jobs from the source."""


@dataclass(frozen=True)
class SourceFetchError(Exception):
    """Raised when a source returns an unrecoverable error."""

    source: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover — trivial
        return f"{self.source}: {self.detail}"


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()
