"""URL-based ATS platform detection.

Each supported ATS has distinctive URL patterns. We match against host
substrings rather than exact hostnames because companies often embed boards
under their own subdomain (e.g. `careers.acme.com/jobs/?gh_jid=...`).
"""
from __future__ import annotations

from urllib.parse import urlparse

from jobforge.application_agent.base import ATSPlatform

# (substring, platform) — first match wins.
_HOST_RULES: tuple[tuple[str, ATSPlatform], ...] = (
    ("greenhouse.io", ATSPlatform.GREENHOUSE),
    ("boards.greenhouse.io", ATSPlatform.GREENHOUSE),
    ("boards-api.greenhouse.io", ATSPlatform.GREENHOUSE),
    ("lever.co", ATSPlatform.LEVER),
    ("jobs.lever.co", ATSPlatform.LEVER),
    ("ashbyhq.com", ATSPlatform.ASHBY),
    ("jobs.ashbyhq.com", ATSPlatform.ASHBY),
)

# Query/path heuristics for embedded boards.
_PATH_HINTS = (
    ("gh_jid=", ATSPlatform.GREENHOUSE),
    ("lever-jobs", ATSPlatform.LEVER),
    ("ashby_jid=", ATSPlatform.ASHBY),
)


def detect_platform(url: str) -> ATSPlatform:
    if not url:
        return ATSPlatform.UNKNOWN
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for substring, platform in _HOST_RULES:
        if substring in host:
            return platform
    blob = f"{parsed.path} {parsed.query}".lower()
    for hint, platform in _PATH_HINTS:
        if hint in blob:
            return platform
    return ATSPlatform.UNKNOWN
