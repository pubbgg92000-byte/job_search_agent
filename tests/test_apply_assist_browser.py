"""Real Chromium integration: PlaywrightChromiumAgent against the mock ATS server.

Marked `@pytest.mark.browser` so the suite can be filtered out when Chromium
isn't available. CI installs Chromium so these run on every PR.

Strategy:
- Stand up `MockATSServer` once per test session.
- For each platform: open the mock apply page, drive the runner through
  fill → ready → submit, and assert the mock server captured the submission.
- All other test cases drive direct PlaywrightChromiumAgent methods to verify
  open/fill/click/upload/screenshot/close work end-to-end.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from jobforge.application_agent.base import ApplicationPackage, ATSPlatform
from jobforge.application_agent.browser import (
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    PlaywrightApplicationAgent,
    SessionRegistry,
)
from tests.fixtures.ats_pages.mock_server import MockATSServer

pytestmark = pytest.mark.browser

playwright_async_api = pytest.importorskip("playwright.async_api")


# ---- fixtures ---------------------------------------------------------


@pytest.fixture
async def mock_ats() -> AsyncIterator[MockATSServer]:
    s = MockATSServer()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


@pytest.fixture
def resume_pdf(tmp_path: Path) -> str:
    # Reuse the existing sample resume from Phase 1 fixtures if present;
    # otherwise synthesize a tiny PDF-shaped file (the mock server only checks
    # filename + length, not real PDF magic).
    real = Path(__file__).parent / "fixtures" / "sample_resume.pdf"
    if real.exists():
        return str(real)
    fake = tmp_path / "synth.pdf"
    fake.write_bytes(b"%PDF-1.4\nsynth\n%%EOF\n")
    return str(fake)


@pytest.fixture
def cover_pdf(tmp_path: Path) -> str:
    p = tmp_path / "cover.pdf"
    p.write_bytes(b"%PDF-1.4\ncover\n%%EOF\n")
    return str(p)


# ---- helpers ----------------------------------------------------------


def _registry_session(reg: SessionRegistry, *, platform: ATSPlatform, url: str) -> Any:
    return reg.create(
        application_id=1,
        platform=platform,
        job_url=url,
        headless=True,
    )


async def _collector() -> tuple[Any, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []

    async def emit(*, session: Any, event_type: str, notes: str | None = None) -> None:
        events.append({"sid": session.id, "type": event_type, "notes": notes})

    return emit, events


def _pkg_greenhouse(resume: str, cover: str) -> ApplicationPackage:
    return ApplicationPackage(
        platform=ATSPlatform.GREENHOUSE,
        job_url="",
        company="Acme",
        title="Engineer",
        applicant_fields={
            "first_name": "Rahul",
            "last_name": "Sample",
            "email": "rahul@example.com",
            "phone": "+1-555",
            "urls[LinkedIn]": "https://linkedin.com/in/rahul",
        },
        resume_path=resume,
        cover_letter_path=cover,
    )


def _pkg_lever(resume: str) -> ApplicationPackage:
    return ApplicationPackage(
        platform=ATSPlatform.LEVER,
        job_url="",
        company="Acme",
        title="Engineer",
        applicant_fields={
            "name": "Rahul Sample",
            "email": "rahul@example.com",
            "phone": "+1-555",
        },
        resume_path=resume,
    )


def _pkg_ashby(resume: str, cover: str) -> ApplicationPackage:
    return ApplicationPackage(
        platform=ATSPlatform.ASHBY,
        job_url="",
        company="Acme",
        title="Engineer",
        applicant_fields={
            "firstName": "Rahul",
            "lastName": "Sample",
            "email": "rahul@example.com",
            "phone": "+1-555",
        },
        resume_path=resume,
        cover_letter_path=cover,
    )


# ---- direct browser-agent smoke ---------------------------------------


@pytest.mark.asyncio
async def test_playwright_chromium_open_returns_navigation_result(mock_ats: MockATSServer) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    a = PlaywrightChromiumAgent(headless=True)
    try:
        result = await a.open(mock_ats.url_for("greenhouse"))
        assert result.status_code == 200
        assert "greenhouse" in result.final_url
        assert result.page_title is not None
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_playwright_chromium_fill_and_screenshot(
    mock_ats: MockATSServer, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    a = PlaywrightChromiumAgent(headless=True)
    try:
        await a.open(mock_ats.url_for("greenhouse"))
        await a.fill('input[name="first_name"]', "Rahul")
        shot = tmp_path / "shot.png"
        await a.screenshot(str(shot))
        assert shot.exists() and shot.stat().st_size > 100
    finally:
        await a.close()


@pytest.mark.asyncio
async def test_playwright_chromium_upload_file(
    mock_ats: MockATSServer, resume_pdf: str
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    a = PlaywrightChromiumAgent(headless=True)
    try:
        await a.open(mock_ats.url_for("greenhouse"))
        await a.upload('input[type="file"][name="resume"]', resume_pdf)
    finally:
        await a.close()


# ---- end-to-end runner per platform -----------------------------------


@pytest.mark.asyncio
async def test_greenhouse_end_to_end(
    mock_ats: MockATSServer, resume_pdf: str, cover_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.GREENHOUSE, url=mock_ats.url_for("greenhouse"))
    emit, _events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    pkg = _pkg_greenhouse(resume_pdf, cover_pdf)
    await agent.fill_form(s, pkg)
    assert s.state == STATE_READY_FOR_REVIEW
    assert all(Path(p).exists() for p in s.screenshot_paths)

    await agent.submit(s)
    assert s.state == STATE_SUBMITTED

    # The mock server must have received the submission with the right fields.
    assert len(mock_ats.submissions["greenhouse"]) == 1
    captured = mock_ats.submissions["greenhouse"][0]
    assert captured.get("first_name") == "Rahul"
    assert captured.get("last_name") == "Sample"
    assert captured.get("email") == "rahul@example.com"
    assert "resume" in captured and captured["resume"]["size"] > 0
    assert "cover_letter" in captured


@pytest.mark.asyncio
async def test_lever_end_to_end(
    mock_ats: MockATSServer, resume_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.LEVER, url=mock_ats.url_for("lever"))
    emit, _events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    pkg = _pkg_lever(resume_pdf)
    await agent.fill_form(s, pkg)
    assert s.state == STATE_READY_FOR_REVIEW
    await agent.submit(s)
    assert s.state == STATE_SUBMITTED

    captured = mock_ats.submissions["lever"][0]
    assert captured.get("name") == "Rahul Sample"  # collapsed single field
    assert captured.get("email") == "rahul@example.com"


@pytest.mark.asyncio
async def test_ashby_end_to_end(
    mock_ats: MockATSServer, resume_pdf: str, cover_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.ASHBY, url=mock_ats.url_for("ashby"))
    emit, _events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    pkg = _pkg_ashby(resume_pdf, cover_pdf)
    await agent.fill_form(s, pkg)
    assert s.state == STATE_READY_FOR_REVIEW
    await agent.submit(s)
    assert s.state == STATE_SUBMITTED

    captured = mock_ats.submissions["ashby"][0]
    assert captured.get("firstName") == "Rahul"
    assert captured.get("lastName") == "Sample"


@pytest.mark.asyncio
async def test_screenshots_grow_per_field_filled(
    mock_ats: MockATSServer, resume_pdf: str, cover_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.GREENHOUSE, url=mock_ats.url_for("greenhouse"))
    emit, _events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    await agent.fill_form(s, _pkg_greenhouse(resume_pdf, cover_pdf))
    # Expect at least: opened, filled-first_name, filled-last_name, filled-email,
    # filled-phone, filled-resume, filled-cover_letter, form-complete.
    assert len(s.screenshot_paths) >= 6


@pytest.mark.asyncio
async def test_runner_records_ready_event_before_submit(
    mock_ats: MockATSServer, resume_pdf: str, cover_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.GREENHOUSE, url=mock_ats.url_for("greenhouse"))
    emit, events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    await agent.fill_form(s, _pkg_greenhouse(resume_pdf, cover_pdf))
    types = [e["type"] for e in events]
    assert types.index("apply_assist.ready_for_review") == len(types) - 1


@pytest.mark.asyncio
async def test_cancel_after_fill_releases_browser(
    mock_ats: MockATSServer, resume_pdf: str, cover_pdf: str, tmp_path: Path
) -> None:
    from jobforge.agents_phase3 import PlaywrightChromiumAgent

    reg = SessionRegistry()
    s = _registry_session(reg, platform=ATSPlatform.GREENHOUSE, url=mock_ats.url_for("greenhouse"))
    emit, _events = await _collector()
    browser = PlaywrightChromiumAgent(headless=True)
    agent = PlaywrightApplicationAgent(browser, emit=emit, screenshot_dir=tmp_path)

    await agent.fill_form(s, _pkg_greenhouse(resume_pdf, cover_pdf))
    await agent.cancel(s, reason="testing cancel")
    assert s.state == "cancelled"
