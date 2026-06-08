"""Phase 3 interface stubs — verify the contracts exist and are abstract."""
from __future__ import annotations

import inspect

import pytest

from jobforge.agents_phase3 import (
    BrowserAgent,
    CompanyResearchAgent,
    PlaywrightAgent,
    TelegramAgent,
)


def test_browser_agent_is_abstract() -> None:
    assert inspect.isabstract(BrowserAgent)


def test_telegram_agent_is_abstract() -> None:
    assert inspect.isabstract(TelegramAgent)


def test_company_research_agent_is_abstract() -> None:
    assert inspect.isabstract(CompanyResearchAgent)


def test_playwright_agent_is_concrete_but_not_implemented() -> None:
    # PlaywrightAgent inherits all abstract methods but provides bodies that raise.
    # It should be instantiable.
    agent = PlaywrightAgent(headless=True)
    assert agent.headless is True


@pytest.mark.asyncio
async def test_playwright_methods_raise_not_implemented() -> None:
    agent = PlaywrightAgent()
    with pytest.raises(NotImplementedError):
        await agent.open("https://example.com")
    with pytest.raises(NotImplementedError):
        await agent.fill("#input", "value")
    with pytest.raises(NotImplementedError):
        await agent.click("#button")
    with pytest.raises(NotImplementedError):
        await agent.upload("#file", "/tmp/x")
    with pytest.raises(NotImplementedError):
        await agent.screenshot("/tmp/x.png")
    with pytest.raises(NotImplementedError):
        await agent.close()
