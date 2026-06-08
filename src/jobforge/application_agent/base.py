"""Core types for the application agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ATSPlatform(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ApplicationPackage:
    """Everything the (future) browser agent needs to submit an application.

    Frozen by design: once built, the package is what gets handed to the next
    step. If something needs to change, build a new package — no in-place
    mutation.
    """

    platform: ATSPlatform
    job_url: str
    company: str | None
    title: str | None
    applicant_fields: dict[str, str]
    resume_path: str | None = None
    cover_letter_path: str | None = None
    custom_questions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "job_url": self.job_url,
            "company": self.company,
            "title": self.title,
            "applicant_fields": dict(self.applicant_fields),
            "resume_path": self.resume_path,
            "cover_letter_path": self.cover_letter_path,
            "custom_questions": list(self.custom_questions),
            "notes": list(self.notes),
        }


class PackageError(Exception):
    """Raised when package assembly can't satisfy a precondition (missing profile, bad URL)."""
