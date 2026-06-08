"""Remotive adapter — https://remotive.com/api/remote-jobs (public JSON)."""
from __future__ import annotations

from typing import Any

import httpx

from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError, safe_str
from jobforge.discovery.normalize import infer_salary, parse_iso_datetime, strip_html

_URL = "https://remotive.com/api/remote-jobs"


class RemotiveAdapter(JobSourceAdapter):
    source = "remotive"

    def parse(self, payload: dict[str, Any]) -> list[RawJob]:
        out: list[RawJob] = []
        for job in payload.get("jobs", []) or []:
            jid = job.get("id")
            url = safe_str(job.get("url"))
            title = safe_str(job.get("title"))
            if not jid or not url or not title:
                continue
            company = safe_str(job.get("company_name")) or "Unknown"
            location = safe_str(job.get("candidate_required_location")) or None
            description = strip_html(job.get("description"))
            posted_at = parse_iso_datetime(
                job.get("publication_date") or job.get("created_at")
            )
            smin, smax, scur = infer_salary(safe_str(job.get("salary")), description)
            out.append(
                RawJob(
                    source=self.source,
                    source_job_id=str(jid),
                    company=company,
                    title=title,
                    location=location,
                    remote=True,
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
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(_URL)
                resp.raise_for_status()
                return self.parse(resp.json())
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
