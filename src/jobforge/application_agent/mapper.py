"""Profile → ATS field-name mapping.

Each ATS expects different field names (`first_name` vs `firstName`, etc.).
The mapper centralizes those naming differences so the rest of the agent
doesn't care which platform it's targeting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from jobforge.application_agent.base import ATSPlatform


@dataclass
class FieldMapper:
    """Maps logical profile fields to the platform's wire names."""

    platform: ATSPlatform

    # Each platform's preferred names for the same logical field.
    _SCHEMAS: ClassVar[dict[ATSPlatform, dict[str, str]]] = {
        ATSPlatform.GREENHOUSE: {
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "email",
            "phone": "phone",
            "location": "location",
            "resume": "resume",
            "cover_letter": "cover_letter",
            "linkedin": "urls[LinkedIn]",
        },
        ATSPlatform.LEVER: {
            "first_name": "name",  # Lever takes a single full-name field
            "last_name": "name",
            "email": "email",
            "phone": "phone",
            "location": "location",
            "resume": "resume",
            "cover_letter": "additionalInformation",
            "linkedin": "urls[0]",
        },
        ATSPlatform.ASHBY: {
            "first_name": "firstName",
            "last_name": "lastName",
            "email": "email",
            "phone": "phone",
            "location": "location",
            "resume": "resume",
            "cover_letter": "coverLetter",
            "linkedin": "linkedinUrl",
        },
    }

    def wire_name(self, logical: str) -> str | None:
        schema = self._SCHEMAS.get(self.platform)
        if schema is None:
            return None
        return schema.get(logical)


def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def map_profile(
    profile: dict[str, Any], platform: ATSPlatform
) -> dict[str, str]:
    """Project a structured profile into a platform-specific flat field dict.

    Only fields actually present in the profile end up in the result — we
    don't manufacture empty strings.
    """
    mapper = FieldMapper(platform=platform)
    out: dict[str, str] = {}

    name = (profile.get("name") or "").strip()
    first, last = _split_name(name)
    for logical, value in (
        ("first_name", first if platform != ATSPlatform.LEVER else name),
        ("last_name", last if platform != ATSPlatform.LEVER else name),
        ("email", profile.get("email")),
        ("phone", profile.get("phone")),
        ("location", profile.get("location")),
        ("linkedin", _find_linkedin(profile)),
    ):
        if not value:
            continue
        wire = mapper.wire_name(logical)
        if not wire:
            continue
        out[wire] = str(value)
    return out


def _find_linkedin(profile: dict[str, Any]) -> str | None:
    for url in profile.get("urls", []) or []:
        if isinstance(url, str) and "linkedin.com" in url.lower():
            return url
    for url in profile.get("links", []) or []:
        if isinstance(url, str) and "linkedin.com" in url.lower():
            return url
    return None
