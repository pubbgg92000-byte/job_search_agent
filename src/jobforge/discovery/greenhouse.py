"""Greenhouse Job Board API adapter.

Public docs: https://developers.greenhouse.io/job-board.html
Endpoint shape: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
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

_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter(JobSourceAdapter):
    source = "greenhouse"

    def __init__(self, board_slug: str, company_override: str | None = None) -> None:
        self.board_slug = board_slug
        self.company_override = company_override

    def parse(self, payload: dict[str, Any]) -> list[RawJob]:
        out: list[RawJob] = []
        for job in payload.get("jobs", []) or []:
            jid = job.get("id")
            if jid is None:
                continue
            title = safe_str(job.get("title"))
            url = safe_str(job.get("absolute_url"))
            if not title or not url:
                continue
            location = safe_str((job.get("location") or {}).get("name")) or None
            description = strip_html(job.get("content"))
            remote = detect_remote(title, location or "", description)
            company = self.company_override or safe_str(
                (job.get("company") or {}).get("name")
            ) or self.board_slug
            posted_at = parse_iso_datetime(
                job.get("updated_at") or job.get("first_published")
            )
            smin, smax, scur = infer_salary(description)
            out.append(
                RawJob(
                    source=self.source,
                    source_job_id=str(jid),
                    company=company,
                    title=title,
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
        url = f"{_BASE}/{self.board_slug}/jobs?content=true"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return self.parse(resp.json())
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
