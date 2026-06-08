"""We Work Remotely RSS adapter.

Public RSS: https://weworkremotely.com/categories/remote-programming-jobs.rss
RSS item shape (ElementTree-friendly):
  <item>
    <title>Company: Senior Engineer</title>
    <link>https://weworkremotely.com/remote-jobs/abc-123</link>
    <pubDate>Tue, 03 Jun 2026 12:34:00 +0000</pubDate>
    <description><![CDATA[...]]></description>
    <region>Worldwide</region>
    <guid>abc-123</guid>
  </item>
"""
from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

from jobforge.discovery.base import JobSourceAdapter, RawJob, SourceFetchError, safe_str
from jobforge.discovery.normalize import infer_salary, strip_html

DEFAULT_CATEGORY = "remote-programming-jobs"


def _split_title(raw: str) -> tuple[str, str]:
    """WWR titles look like 'Company: Role'. Split on the first colon."""
    if ":" in raw:
        company, _, role = raw.partition(":")
        return company.strip(), role.strip()
    return "Unknown", raw.strip()


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class WWRAdapter(JobSourceAdapter):
    source = "wwr"

    def __init__(self, category: str = DEFAULT_CATEGORY) -> None:
        self.category = category

    def parse(self, xml_text: str) -> list[RawJob]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        out: list[RawJob] = []
        for item in root.iter("item"):
            link = safe_str(item.findtext("link") or "")
            guid = safe_str(item.findtext("guid") or "") or link
            title_raw = safe_str(item.findtext("title"))
            if not link or not guid or not title_raw:
                continue
            company, title = _split_title(title_raw)
            description = strip_html(item.findtext("description"))
            region = safe_str(item.findtext("region")) or None
            posted_at = _parse_rss_date(item.findtext("pubDate"))
            smin, smax, scur = infer_salary(description)
            out.append(
                RawJob(
                    source=self.source,
                    source_job_id=guid,
                    company=company,
                    title=title,
                    location=region,
                    remote=True,
                    description=description,
                    url=link,
                    posted_at=posted_at,
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=scur,
                )
            )
        return out

    async def fetch_jobs(self) -> list[RawJob]:
        url = f"https://weworkremotely.com/categories/{self.category}.rss"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return self.parse(resp.text)
        except httpx.HTTPError as exc:
            raise SourceFetchError(self.source, str(exc)) from exc
