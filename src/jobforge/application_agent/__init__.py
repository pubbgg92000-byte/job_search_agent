"""Application agent foundation.

Phase 2B ships only the architecture: ATS platform detection, field mapping,
and ApplicationPackage assembly. No browser automation. No submission. Phase
3 will implement actual fill-and-submit on top of this scaffold.

Why no browser yet:
- Browser automation has different operational characteristics (headful vs
  headless, anti-bot detection, session storage). Worth a dedicated phase.
- The architecture here is testable in isolation today.
"""
from __future__ import annotations

from jobforge.application_agent.base import (
    ApplicationPackage,
    ATSPlatform,
    PackageError,
)
from jobforge.application_agent.detector import detect_platform
from jobforge.application_agent.mapper import FieldMapper, map_profile
from jobforge.application_agent.package import prepare_package

__all__ = [
    "ATSPlatform",
    "ApplicationPackage",
    "FieldMapper",
    "PackageError",
    "detect_platform",
    "map_profile",
    "prepare_package",
]
