"""Pure parsing tests for the 6 source adapters.

We hit `parse()` with stored fixtures — no network. Tests assert the natural-key
(`source`, `source_job_id`), key normalization, remote detection, and salary
inference.
"""
from __future__ import annotations

import json
from pathlib import Path

from jobforge.discovery.ashby import AshbyAdapter
from jobforge.discovery.greenhouse import GreenhouseAdapter
from jobforge.discovery.lever import LeverAdapter
from jobforge.discovery.remoteok import RemoteOKAdapter
from jobforge.discovery.remotive import RemotiveAdapter
from jobforge.discovery.wwr import WWRAdapter

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "adapters"


def _load_json(name: str):
    return json.loads((FIXTURE_DIR / name).read_text())


# ---------- Greenhouse ----------


def test_greenhouse_parse_returns_two_jobs_with_natural_keys() -> None:
    payload = _load_json("greenhouse.json")
    jobs = GreenhouseAdapter("acmecorp").parse(payload)
    assert {j.source_job_id for j in jobs} == {"4567890", "4567891"}
    assert all(j.source == "greenhouse" for j in jobs)


def test_greenhouse_uses_company_name_when_present() -> None:
    payload = _load_json("greenhouse.json")
    jobs = GreenhouseAdapter("acmecorp").parse(payload)
    first = next(j for j in jobs if j.source_job_id == "4567890")
    assert first.company == "Acme Corp"
    assert first.title == "Senior Backend Engineer"
    assert first.location == "San Francisco, CA"


def test_greenhouse_strips_html_and_extracts_salary() -> None:
    payload = _load_json("greenhouse.json")
    jobs = GreenhouseAdapter("acmecorp").parse(payload)
    first = next(j for j in jobs if j.source_job_id == "4567890")
    assert "<p>" not in first.description
    assert "we're" in first.description.lower()  # HTML entity decoded
    assert first.salary_min == 160000
    assert first.salary_max == 200000
    assert first.salary_currency == "USD"
    assert first.remote is True


def test_greenhouse_drops_jobs_without_id_or_url() -> None:
    payload = {"jobs": [{"title": "No ID"}, {"id": 1, "title": ""}]}
    assert GreenhouseAdapter("x").parse(payload) == []


def test_greenhouse_company_override_wins_over_payload() -> None:
    payload = _load_json("greenhouse.json")
    jobs = GreenhouseAdapter("acmecorp", company_override="Override Inc").parse(payload)
    assert all(j.company == "Override Inc" for j in jobs)


# ---------- Lever ----------


def test_lever_parse_returns_two_jobs() -> None:
    payload = _load_json("lever.json")
    jobs = LeverAdapter("exampleco").parse(payload)
    assert {j.source_job_id for j in jobs} == {"abc-123", "def-456"}


def test_lever_workplace_type_remote_flips_remote_flag() -> None:
    payload = _load_json("lever.json")
    jobs = LeverAdapter("exampleco").parse(payload)
    remote_job = next(j for j in jobs if j.source_job_id == "abc-123")
    onsite_job = next(j for j in jobs if j.source_job_id == "def-456")
    assert remote_job.remote is True
    assert onsite_job.remote is False


def test_lever_uses_team_in_title() -> None:
    payload = _load_json("lever.json")
    jobs = LeverAdapter("exampleco").parse(payload)
    first = next(j for j in jobs if j.source_job_id == "abc-123")
    assert "(Backend)" in first.title


def test_lever_falls_back_to_org_slug_for_company() -> None:
    payload = _load_json("lever.json")
    jobs = LeverAdapter("exampleco").parse(payload)
    assert all(j.company == "exampleco" for j in jobs)


# ---------- Ashby ----------


def test_ashby_parse_returns_two_jobs_with_remote_flag() -> None:
    payload = _load_json("ashby.json")
    jobs = AshbyAdapter("orgx").parse(payload)
    ids = {j.source_job_id: j for j in jobs}
    assert set(ids) == {"ashby-1", "ashby-2"}
    assert ids["ashby-1"].remote is False
    assert ids["ashby-2"].remote is True


def test_ashby_extracts_organization_name() -> None:
    jobs = AshbyAdapter("orgx").parse(_load_json("ashby.json"))
    assert any(j.company == "OrgX" for j in jobs)


def test_ashby_extracts_salary_from_description() -> None:
    jobs = AshbyAdapter("orgx").parse(_load_json("ashby.json"))
    first = next(j for j in jobs if j.source_job_id == "ashby-1")
    assert first.salary_min == 150000 and first.salary_max == 190000
    assert first.salary_currency == "USD"


# ---------- RemoteOK ----------


def test_remoteok_skips_legal_header_entry() -> None:
    payload = _load_json("remoteok.json")
    jobs = RemoteOKAdapter().parse(payload)
    assert {j.source_job_id for j in jobs} == {"rok-1", "rok-2"}
    assert all(j.remote for j in jobs)


def test_remoteok_uses_explicit_salary_when_set() -> None:
    jobs = RemoteOKAdapter().parse(_load_json("remoteok.json"))
    rok1 = next(j for j in jobs if j.source_job_id == "rok-1")
    assert rok1.salary_min == 120000 and rok1.salary_max == 160000
    assert rok1.salary_currency == "USD"


def test_remoteok_handles_missing_salary_gracefully() -> None:
    jobs = RemoteOKAdapter().parse(_load_json("remoteok.json"))
    rok2 = next(j for j in jobs if j.source_job_id == "rok-2")
    assert rok2.salary_min is None and rok2.salary_max is None


# ---------- Remotive ----------


def test_remotive_parse_returns_two_jobs() -> None:
    payload = _load_json("remotive.json")
    jobs = RemotiveAdapter().parse(payload)
    assert {j.source_job_id for j in jobs} == {"555111", "555222"}
    assert all(j.remote for j in jobs)


def test_remotive_extracts_salary_from_salary_field() -> None:
    jobs = RemotiveAdapter().parse(_load_json("remotive.json"))
    first = next(j for j in jobs if j.source_job_id == "555111")
    assert first.salary_min == 70000 and first.salary_max == 90000
    assert first.salary_currency == "EUR"


# ---------- WeWorkRemotely ----------


def test_wwr_parse_returns_two_jobs_from_rss() -> None:
    xml = (FIXTURE_DIR / "wwr.xml").read_text()
    jobs = WWRAdapter().parse(xml)
    assert {j.source_job_id for j in jobs} == {"wwr-1", "wwr-2"}
    assert all(j.remote for j in jobs)


def test_wwr_splits_company_from_title() -> None:
    xml = (FIXTURE_DIR / "wwr.xml").read_text()
    jobs = WWRAdapter().parse(xml)
    first = next(j for j in jobs if j.source_job_id == "wwr-1")
    assert first.company == "HappyCorp"
    assert first.title == "Senior Ruby Developer"


def test_wwr_handles_malformed_rss_gracefully() -> None:
    assert WWRAdapter().parse("<not-rss>") == []


def test_wwr_extracts_salary_from_description() -> None:
    xml = (FIXTURE_DIR / "wwr.xml").read_text()
    jobs = WWRAdapter().parse(xml)
    first = next(j for j in jobs if j.source_job_id == "wwr-1")
    assert first.salary_min == 130000 and first.salary_max == 170000
    assert first.salary_currency == "USD"
