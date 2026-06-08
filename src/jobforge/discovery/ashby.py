"""Ashby public job board API.

Public docs: https://developers.ashbyhq.com/reference/jobpostings
Endpoint: https://api.ashbyhq.com/posting-api/job-board/{org_slug}
"""
from __future__ import annotations

from typing import Any

import httpx

from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError, safe_str
from jobforge.discovery.normalize import (
    detect_remote,
    infer_salary,
    parse_iso_datetime,
    strip_html,
)

_BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyAdapter(JobSourceAdapter):
    source = "ashby"

    def __init__(self, org_slug: str, company_override: str | None = None) -> None:
        self.org_slug = org_slug
        self.company_override = company_override

    def parse(self, payload: dict[str, Any]) -> list[RawJob]:
        out: list[RawJob] = []
        for job in payload.get("jobs", []) or []:
            jid = job.get("id")
            url = safe_str(job.get("jobUrl") or job.get("applyUrl"))
            title = safe_str(job.get("title"))
            if not jid or not url or not title:
                continue
            location = safe_str(job.get("locationName") or job.get("location")) or None
            description = strip_html(
                job.get("descriptionHtml") or job.get("descriptionPlain")
            )
            is_remote = bool(job.get("isRemote")) or detect_remote(
                location or "", description
            )
            posted_at = parse_iso_datetime(job.get("publishedAt") or job.get("updatedAt"))
            smin, smax, scur = infer_salary(description)
            company = (
                self.company_override
                or safe_str(job.get("organizationName"))
                or self.org_slug
            )
            out.append(
                RawJob(
                    source=self.source,
                    source_job_id=str(jid),
                    company=company,
                    title=title,
                    location=location,
                    remote=is_remote,
                    description=description,
                    url=url,
                    posted_at=posted_at,
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=scur,
                )
            )
        return out

    async def fetch_jobs(self) -> list[RawJob]:
        url = f"{_BASE}/{self.org_slug}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return self.parse(resp.json())
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
