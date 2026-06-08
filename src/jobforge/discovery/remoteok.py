"""RemoteOK adapter — `https://remoteok.com/api` (JSON list, first entry is metadata)."""
from __future__ import annotations

from typing import Any

import httpx

from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError, safe_str
from jobforge.discovery.normalize import (
    infer_salary,
    parse_iso_datetime,
    parse_unix_timestamp,
    strip_html,
)

_URL = "https://remoteok.com/api"


class RemoteOKAdapter(JobSourceAdapter):
    source = "remoteok"

    def parse(self, payload: list[dict[str, Any]]) -> list[RawJob]:
        out: list[RawJob] = []
        if not payload:
            return out
        # First entry is a legal-disclaimer header — skip if it doesn't look like a job.
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if entry.get("legal") and "slug" not in entry and "position" not in entry:
                continue
            jid = entry.get("id") or entry.get("slug")
            url = safe_str(entry.get("url") or entry.get("apply_url"))
            title = safe_str(entry.get("position") or entry.get("title"))
            if not jid or not url or not title:
                continue
            company = safe_str(entry.get("company")) or "Unknown"
            location = safe_str(entry.get("location")) or None
            description = strip_html(entry.get("description"))
            # RemoteOK jobs are remote-by-definition.
            remote = True
            posted_at = parse_iso_datetime(safe_str(entry.get("date")) or None) or parse_unix_timestamp(entry.get("epoch"))
            smin = entry.get("salary_min")
            smax = entry.get("salary_max")
            scur = "USD" if smin or smax else None
            if not (isinstance(smin, int) and isinstance(smax, int) and smin > 0 and smax >= smin):
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
        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                headers={"User-Agent": "jobforge/0.1 (+https://example.invalid)"},
            ) as client:
                resp = await client.get(_URL)
                resp.raise_for_status()
                return self.parse(resp.json())
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
