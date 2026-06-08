"""Runner state machine — fill → ready → submit / cancel / fail.

Uses a FakeBrowser to avoid needing real Chromium. Coverage:
- happy path: fill_form transitions in_progress → ready_for_review
- screenshots accumulate per step
- submit transitions ready → submitted; closes browser
- submit refused outside ready_for_review
- cancel from in_progress or ready_for_review
- fill_form failure → FAILED state + apply_assist.failed event + browser closed
- unknown platform refused
- selector with no fallback raising surfaces as FAILED
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobforge.agents_phase3.browser import BrowserAgent, NavigationResult
from jobforge.application_agent.base import ApplicationPackage, ATSPlatform
from jobforge.application_agent.browser import (
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_IN_PROGRESS,
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    PlaywrightApplicationAgent,
    RunnerError,
    SessionRegistry,
)


class FakeBrowser(BrowserAgent):
    """In-memory stub: records each operation. Optionally fails on selectors."""

    def __init__(self, *, fail_on_selector: str | None = None, fail_on_open: bool = False) -> None:
        self.opened: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.shots: list[str] = []
        self.closed = False
        self.fail_on_selector = fail_on_selector
        self.fail_on_open = fail_on_open

    async def open(self, url: str) -> NavigationResult:
        if self.fail_on_open:
            raise RuntimeError("synthetic open failure")
        self.opened.append(url)
        return NavigationResult(final_url=url, status_code=200, page_title="mock")

    async def fill(self, selector: str, value: str) -> None:
        if self.fail_on_selector == selector:
            raise RuntimeError(f"synthetic fill failure: {selector}")
        self.fills.append((selector, value))

    async def click(self, selector: str) -> None:
        if self.fail_on_selector == selector:
            raise RuntimeError(f"synthetic click failure: {selector}")
        self.clicks.append(selector)

    async def upload(self, selector: str, file_path: str) -> None:
        if self.fail_on_selector == selector:
            raise RuntimeError(f"synthetic upload failure: {selector}")
        self.uploads.append((selector, file_path))

    async def screenshot(self, path: str) -> None:
        # Touch the file so any code checking existence sees something there.
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic
        self.shots.append(path)

    async def close(self) -> None:
        self.closed = True


def _collector() -> tuple[Any, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []

    async def emit(*, session: Any, event_type: str, notes: str | None = None) -> None:
        events.append({"sid": session.id, "type": event_type, "notes": notes})

    return emit, events


def _make_session(reg: SessionRegistry, *, platform: ATSPlatform = ATSPlatform.GREENHOUSE) -> Any:
    return reg.create(
        application_id=42,
        platform=platform,
        job_url="https://boards.greenhouse.io/x/jobs/1",
        headless=True,
    )


def _pkg(platform: ATSPlatform, *, with_files: bool = True) -> ApplicationPackage:
    return ApplicationPackage(
        platform=platform,
        job_url="https://boards.greenhouse.io/x/jobs/1",
        company="Acme",
        title="Engineer",
        applicant_fields={
            "first_name": "Rahul",
            "last_name": "Sample",
            "email": "rahul@example.com",
            "phone": "+1-555",
            "urls[LinkedIn]": "https://linkedin.com/in/rahul",
            "name": "Rahul Sample",
            "firstName": "Rahul",
            "lastName": "Sample",
            "linkedinUrl": "https://linkedin.com/in/rahul",
        },
        resume_path="/tmp/resume.pdf" if with_files else None,
        cover_letter_path="/tmp/cover.pdf" if with_files else None,
    )


@pytest.fixture
def tmp_screens(tmp_path: Path) -> Path:
    d = tmp_path / "shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.asyncio
async def test_fill_form_happy_path_transitions_to_ready(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)

    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))

    assert s.state == STATE_READY_FOR_REVIEW
    assert s.ready_for_review_at is not None
    assert s.screenshot_paths  # at least one
    assert fb.opened == ["https://boards.greenhouse.io/x/jobs/1"]
    types = [e["type"] for e in events]
    assert "apply_assist.form_started" in types
    assert "apply_assist.form_completed" in types
    assert "apply_assist.ready_for_review" in types
    assert types.index("apply_assist.form_started") < types.index("apply_assist.ready_for_review")


@pytest.mark.asyncio
async def test_fill_form_uploads_resume_and_cover_letter(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)

    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))

    upload_paths = [v for _sel, v in fb.uploads]
    assert "/tmp/resume.pdf" in upload_paths
    assert "/tmp/cover.pdf" in upload_paths


@pytest.mark.asyncio
async def test_fill_form_skips_fields_missing_from_package(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg, platform=ATSPlatform.LEVER)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    pkg = ApplicationPackage(
        platform=ATSPlatform.LEVER,
        job_url="https://jobs.lever.co/x/y",
        company="X",
        title="Eng",
        applicant_fields={"name": "Rahul Sample", "email": "r@x.test"},
        resume_path="/tmp/resume.pdf",
    )
    await agent.fill_form(s, pkg)
    assert s.state == STATE_READY_FOR_REVIEW
    assert "phone" in s.extra["skipped_fields"]
    assert "name" in s.extra["filled_fields"]


@pytest.mark.asyncio
async def test_fill_form_refuses_unknown_platform(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg, platform=ATSPlatform.UNKNOWN)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    with pytest.raises(RunnerError):
        await agent.fill_form(s, _pkg(ATSPlatform.UNKNOWN))
    assert s.state == STATE_FAILED
    assert any(e["type"] == "apply_assist.failed" for e in events)
    assert fb.closed is True


@pytest.mark.asyncio
async def test_fill_form_failure_during_open_marks_failed(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser(fail_on_open=True)
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    with pytest.raises(RunnerError):
        await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    assert s.state == STATE_FAILED
    assert s.error_message is not None and "open" in s.error_message
    assert any(e["type"] == "apply_assist.failed" for e in events)
    assert fb.closed is True


@pytest.mark.asyncio
async def test_submit_refused_outside_ready_for_review(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    assert s.state == STATE_IN_PROGRESS
    with pytest.raises(RunnerError):
        await agent.submit(s)


@pytest.mark.asyncio
async def test_submit_happy_path(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    await agent.submit(s)
    assert s.state == STATE_SUBMITTED
    assert s.completed_at is not None
    assert any(e["type"] == "apply_assist.submitted" for e in events)
    assert fb.closed is True
    assert fb.clicks  # submit click recorded


@pytest.mark.asyncio
async def test_submit_failure_marks_failed(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    # Re-create a browser that will fail on the submit selector.
    fb2 = FakeBrowser(fail_on_selector='input[type="submit"][value*="Submit"]')
    agent2 = PlaywrightApplicationAgent(fb2, emit=emit, screenshot_dir=tmp_screens)
    with pytest.raises(RunnerError):
        await agent2.submit(s)
    assert s.state == STATE_FAILED
    assert any(e["type"] == "apply_assist.failed" for e in events)
    assert fb2.closed is True


@pytest.mark.asyncio
async def test_cancel_from_ready_for_review(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    await agent.cancel(s, reason="changed my mind")
    assert s.state == STATE_CANCELLED
    assert s.error_message == "changed my mind"
    assert any(e["type"] == "apply_assist.cancelled" for e in events)
    assert fb.closed is True


@pytest.mark.asyncio
async def test_cancel_from_in_progress(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.cancel(s)
    assert s.state == STATE_CANCELLED
    assert any(e["type"] == "apply_assist.cancelled" for e in events)


@pytest.mark.asyncio
async def test_fill_form_with_lever_does_not_emit_split_name(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg, platform=ATSPlatform.LEVER)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.LEVER))
    filled_selectors = [sel for sel, _v in fb.fills]
    assert 'input[name="name"]' in filled_selectors
    assert 'input[name="first_name"]' not in filled_selectors


@pytest.mark.asyncio
async def test_fill_form_with_ashby_uses_camelcase_fields(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg, platform=ATSPlatform.ASHBY)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.ASHBY))
    filled_selectors = [sel for sel, _v in fb.fills]
    assert any("firstName" in sel for sel in filled_selectors)
    assert any("lastName" in sel for sel in filled_selectors)


@pytest.mark.asyncio
async def test_screenshot_files_are_created_on_disk(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    fb = FakeBrowser()
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    for p in s.screenshot_paths:
        assert Path(p).exists(), f"missing screenshot {p}"


@pytest.mark.asyncio
async def test_fallback_selector_used_when_primary_raises(tmp_screens: Path) -> None:
    reg = SessionRegistry()
    s = _make_session(reg)
    # Make ONLY the primary first_name selector fail; fallback should win.
    fb = FakeBrowser(fail_on_selector='input[name="first_name"]')
    emit, _events = _collector()
    agent = PlaywrightApplicationAgent(fb, emit=emit, screenshot_dir=tmp_screens)
    await agent.fill_form(s, _pkg(ATSPlatform.GREENHOUSE))
    fallback_used = any(sel == 'input[autocomplete="given-name"]' for sel, _v in fb.fills)
    assert fallback_used
    assert s.state == STATE_READY_FOR_REVIEW
