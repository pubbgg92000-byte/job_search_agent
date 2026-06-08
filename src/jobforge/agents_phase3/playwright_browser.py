"""Concrete `BrowserAgent` backed by `playwright.async_api`.

Lives next to `browser.py` (the ABC) rather than inside `application_agent/`
because Playwright is a generic browser driver, not application-agent-specific.

Lazy-imports `playwright` so importing this module never errors when Playwright
isn't installed (e.g. environments running only unit tests). Construction
errors raise `BrowserUnavailable`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jobforge.agents_phase3.browser import BrowserAgent, NavigationResult
from jobforge.logging_setup import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

log = get_logger("jobforge.playwright_browser")


class BrowserUnavailable(RuntimeError):
    """Playwright import failed or Chromium isn't installed."""


class PlaywrightChromiumAgent(BrowserAgent):
    """Concrete BrowserAgent. One agent == one Chromium context == one Page.

    Reuses a single Page per agent for the duration of an apply-assist session.
    The runner expects the page to retain its DOM state between fill steps and
    the eventual submit click, so we deliberately do NOT spin a fresh context
    per call.
    """

    def __init__(self, *, headless: bool = True, step_timeout_ms: int = 15000) -> None:
        self.headless = headless
        self.step_timeout_ms = step_timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _ensure_page(self) -> Page:
        if self._page is not None:
            return self._page
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover — defensive
            raise BrowserUnavailable("playwright not installed") from exc
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context()
            self._context.set_default_timeout(self.step_timeout_ms)
            self._page = await self._context.new_page()
        except Exception as exc:
            await self.close()
            raise BrowserUnavailable(f"Chromium launch failed: {exc}") from exc
        return self._page

    async def open(self, url: str) -> NavigationResult:
        page = await self._ensure_page()
        response: Any = await page.goto(url, wait_until="domcontentloaded")
        status = response.status if response is not None else None
        title: str | None = None
        try:
            title = await page.title()
        except Exception:
            title = None
        return NavigationResult(final_url=page.url, status_code=status, page_title=title)

    async def fill(self, selector: str, value: str) -> None:
        page = await self._ensure_page()
        await page.fill(selector, value)

    async def click(self, selector: str) -> None:
        page = await self._ensure_page()
        await page.click(selector)

    async def upload(self, selector: str, file_path: str) -> None:
        page = await self._ensure_page()
        await page.set_input_files(selector, file_path)

    async def screenshot(self, path: str) -> None:
        page = await self._ensure_page()
        await page.screenshot(path=path, full_page=True)

    async def close(self) -> None:
        # Order matters: page → context → browser → playwright. Swallow
        # downstream errors so the upstream caller's primary error wins.
        for closer in (
            self._page,
            self._context,
            self._browser,
        ):
            if closer is not None:
                try:
                    await closer.close()
                except Exception as exc:
                    log.warning("playwright.close.failed", extra={"error": str(exc)})
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                log.warning("playwright.stop.failed", extra={"error": str(exc)})
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
