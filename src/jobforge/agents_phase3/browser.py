"""Browser automation contracts. Phase 3 implementations go elsewhere."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NavigationResult:
    final_url: str
    status_code: int | None
    page_title: str | None


class BrowserAgent(ABC):
    """Abstract browser driver. Sync semantics intentionally not enforced — the
    implementation may be async (Playwright) or thread-blocking (Selenium)."""

    @abstractmethod
    async def open(self, url: str) -> NavigationResult: ...

    @abstractmethod
    async def fill(self, selector: str, value: str) -> None: ...

    @abstractmethod
    async def click(self, selector: str) -> None: ...

    @abstractmethod
    async def upload(self, selector: str, file_path: str) -> None: ...

    @abstractmethod
    async def screenshot(self, path: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class PlaywrightAgent(BrowserAgent):
    """Placeholder for the Phase 3 Playwright-backed implementation.

    The whole point of Phase 2B is to NOT build this yet. The class exists so
    application_agent code can be typed against it.
    """

    def __init__(self, *, headless: bool = True, **_: Any) -> None:
        self.headless = headless

    async def open(self, url: str) -> NavigationResult:
        raise NotImplementedError("PlaywrightAgent.open is Phase 3 work")

    async def fill(self, selector: str, value: str) -> None:
        raise NotImplementedError("PlaywrightAgent.fill is Phase 3 work")

    async def click(self, selector: str) -> None:
        raise NotImplementedError("PlaywrightAgent.click is Phase 3 work")

    async def upload(self, selector: str, file_path: str) -> None:
        raise NotImplementedError("PlaywrightAgent.upload is Phase 3 work")

    async def screenshot(self, path: str) -> None:
        raise NotImplementedError("PlaywrightAgent.screenshot is Phase 3 work")

    async def close(self) -> None:
        raise NotImplementedError("PlaywrightAgent.close is Phase 3 work")
