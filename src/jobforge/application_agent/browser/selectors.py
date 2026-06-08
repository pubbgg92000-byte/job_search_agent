"""Per-ATS DOM selector maps.

Distinct from `application_agent.mapper`: that maps logical names to JSON-API
wire names (e.g. `urls[LinkedIn]`). This maps logical names to CSS/Playwright
selectors usable by `page.locator(...)`.

Selectors are hand-curated against the anonymized HTML fixtures under
`tests/fixtures/ats_pages/`. Each spec carries a primary selector + a list of
fallbacks tried in order. When a logical field has no spec for the platform,
the runner records it in the session's `extra_json.skipped_fields` and moves
on rather than failing the whole flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from jobforge.application_agent.base import ATSPlatform

SelectorKind = Literal["text", "file", "submit"]


@dataclass(frozen=True)
class SelectorSpec:
    primary: str
    fallbacks: tuple[str, ...] = field(default_factory=tuple)
    kind: SelectorKind = "text"

    def candidates(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


# Logical field names the runner knows how to fill. The mapper already produces
# wire names — but for the browser we work in logical space. Any logical key
# missing from a platform's map is treated as "ATS doesn't expose this field
# on its standard form" and skipped silently with a note.
_SELECTORS: dict[ATSPlatform, dict[str, SelectorSpec]] = {
    ATSPlatform.GREENHOUSE: {
        "first_name": SelectorSpec(
            'input[name="first_name"]',
            ('input[autocomplete="given-name"]',),
        ),
        "last_name": SelectorSpec(
            'input[name="last_name"]',
            ('input[autocomplete="family-name"]',),
        ),
        "email": SelectorSpec('input[name="email"]'),
        "phone": SelectorSpec('input[name="phone"]'),
        "location": SelectorSpec(
            'input[name="job_application[location]"]',
            ('input[name="location"]',),
        ),
        "linkedin": SelectorSpec(
            'input[name="job_application[answers_attributes][0][text_value]"]',
            ('input[aria-label*="LinkedIn"]',),
        ),
        "resume": SelectorSpec(
            'input[type="file"][name="resume"]',
            ('input[type="file"][id="resume"]',),
            kind="file",
        ),
        "cover_letter": SelectorSpec(
            'input[type="file"][name="cover_letter"]',
            ('input[type="file"][id="cover_letter"]',),
            kind="file",
        ),
        "submit": SelectorSpec(
            'input[type="submit"][value*="Submit"]',
            ('button[type="submit"]',),
            kind="submit",
        ),
    },
    ATSPlatform.LEVER: {
        # Lever collapses first/last into a single 'name' field. The runner
        # detects this by looking up logical "name" first.
        "name": SelectorSpec(
            'input[name="name"]',
            ('input[autocomplete="name"]',),
        ),
        "email": SelectorSpec('input[name="email"]'),
        "phone": SelectorSpec('input[name="phone"]'),
        "location": SelectorSpec('input[name="location"]'),
        "linkedin": SelectorSpec(
            'input[name="urls[LinkedIn]"]',
            ('input[aria-label*="LinkedIn"]',),
        ),
        "resume": SelectorSpec(
            'input[type="file"][name="resume"]',
            ('input[type="file"]',),
            kind="file",
        ),
        "cover_letter": SelectorSpec(
            'textarea[name="additionalInformation"]',
        ),
        "submit": SelectorSpec(
            'button[data-qa="btn-submit"]',
            ('button[type="submit"]',),
            kind="submit",
        ),
    },
    ATSPlatform.ASHBY: {
        "first_name": SelectorSpec(
            'input[name="firstName"]',
            ('[aria-label="First Name"]',),
        ),
        "last_name": SelectorSpec(
            'input[name="lastName"]',
            ('[aria-label="Last Name"]',),
        ),
        "email": SelectorSpec(
            'input[name="email"]',
            ('[aria-label="Email"]',),
        ),
        "phone": SelectorSpec('input[name="phone"]'),
        "location": SelectorSpec('input[name="location"]'),
        "linkedin": SelectorSpec('input[name="linkedinUrl"]'),
        "resume": SelectorSpec(
            'input[type="file"][name="resume"]',
            ('input[type="file"]',),
            kind="file",
        ),
        "cover_letter": SelectorSpec(
            'input[type="file"][name="coverLetter"]',
            kind="file",
        ),
        "submit": SelectorSpec(
            'button:has-text("Submit Application")',
            ('button[type="submit"]',),
            kind="submit",
        ),
    },
}


def selectors_for(platform: ATSPlatform) -> dict[str, SelectorSpec]:
    """Return the selector map for `platform` (empty dict for UNKNOWN)."""
    return dict(_SELECTORS.get(platform, {}))


def selector_for(platform: ATSPlatform, logical_field: str) -> SelectorSpec | None:
    return _SELECTORS.get(platform, {}).get(logical_field)


def supported_platforms() -> tuple[ATSPlatform, ...]:
    return tuple(_SELECTORS.keys())


# Logical fields the runner attempts to fill before declaring a form ready.
# Order matters: name fields first (so Lever's collapsed name lookup happens
# before splitting), then contact, then files, never submit.
FILLABLE_FIELDS_ORDER: tuple[str, ...] = (
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "location",
    "linkedin",
    "resume",
    "cover_letter",
)
