"""Lever public postings API.

Public docs: https://help.lever.co/hc/en-us/articles/360001146712
Endpoint shape: https://api.lever.co/v0/postings/{org}?mode=json
"""
from __future__ import annotations

from typing import Any

import httpx

from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError, safe_str
from jobforge.discovery.normalize import (
    detect_remote,
    infer_salary,
    parse_iso_datetime,
    parse_unix_timestamp,
    strip_html,
)

_BASE = "https://api.lever.co/v0/postings"


class LeverAdapter(JobSourceAdapter):
    source = "lever"

    def __init__(self, org_slug: str, company_override: str | None = None) -> None:
        self.org_slug = org_slug
        self.company_override = company_override

    def parse(self, payload: list[dict[str, Any]]) -> list[RawJob]:
        out: list[RawJob] = []
        for job in payload or []:
            jid = job.get("id")
            url = safe_str(job.get("hostedUrl") or job.get("applyUrl"))
            title = safe_str(job.get("text"))
            if not jid or not url or not title:
                continue

            categories = job.get("categories") or {}
            location = safe_str(categories.get("location")) or None
            team = safe_str(categories.get("team"))
            commitment = safe_str(categories.get("commitment"))
            workplace_type = safe_str(categories.get("workplaceType"))

            description = strip_html(
                job.get("descriptionPlain") or job.get("description")
            )
            remote = (
                workplace_type.lower() == "remote"
                or detect_remote(location or "", description, commitment)
            )

            posted_at = parse_unix_timestamp(job.get("createdAt")) or parse_iso_datetime(
                safe_str(job.get("createdAt")) or None
            )
            smin, smax, scur = infer_salary(description)

            out.append(
                RawJob(
                    source=self.source,
                    source_job_id=str(jid),
                    company=self.company_override or self.org_slug,
                    title=title if not team else f"{title} ({team})",
                    location=location,
                    remote=remote,
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
        url = f"{_BASE}/{self.org_slug}?mode=json"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return self.parse(resp.json())
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
