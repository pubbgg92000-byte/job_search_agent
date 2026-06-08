"""Assemble an `ApplicationPackage` from a profile + job + optional artifact."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jobforge.application_agent.base import ApplicationPackage, ATSPlatform, PackageError
from jobforge.application_agent.detector import detect_platform
from jobforge.application_agent.mapper import map_profile
from jobforge.db.models import DiscoveredJob, Profile, TailoredArtifact
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.application_agent")


async def prepare_package(
    *,
    profile_id: int,
    job_id: int | None = None,
    job_url: str | None = None,
    company: str | None = None,
    title: str | None = None,
    artifact_id: int | None = None,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
) -> ApplicationPackage:
    """Build an ApplicationPackage. Either job_id (→ discovered_jobs) or job_url is required.

    No I/O against the target ATS. No submission. This is pure assembly.
    """
    async with session_scope() as session:
        profile = await session.get(Profile, profile_id)
        if profile is None:
            raise PackageError(f"profile {profile_id} not found")
        parsed = profile.parsed_json

        url = job_url
        company_name = company
        job_title = title
        if job_id is not None:
            job = await session.get(DiscoveredJob, job_id)
            if job is None:
                raise PackageError(f"discovered_job {job_id} not found")
            url = url or job.url
            company_name = company_name or job.company
            job_title = job_title or job.title
        if not url:
            raise PackageError("either job_id or job_url is required")

        if artifact_id is not None:
            artifact = await session.get(TailoredArtifact, artifact_id)
            if artifact is None:
                raise PackageError(f"artifact {artifact_id} not found")

    platform = detect_platform(url)
    fields = map_profile(parsed, platform)
    notes: list[str] = []
    if platform == ATSPlatform.UNKNOWN:
        notes.append(
            "Could not detect ATS platform from URL — manual review required."
        )
    if not fields.get("email") and not fields.get("Email"):
        notes.append("Profile missing email; ATS will almost certainly reject this.")
    if resume_path and not Path(resume_path).exists():
        notes.append(f"resume_path {resume_path} does not exist on disk")
    if cover_letter_path and not Path(cover_letter_path).exists():
        notes.append(
            f"cover_letter_path {cover_letter_path} does not exist on disk"
        )

    log.info(
        "application_agent.package.built",
        extra={
            "platform": platform.value,
            "company": company_name,
            "title": job_title,
            "field_count": len(fields),
            "notes": notes,
        },
    )
    return ApplicationPackage(
        platform=platform,
        job_url=url,
        company=company_name,
        title=job_title,
        applicant_fields=fields,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        notes=notes,
    )


def package_to_dict(pkg: ApplicationPackage) -> dict[str, Any]:
    return pkg.to_dict()
