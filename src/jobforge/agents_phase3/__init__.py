"""Phase 3 agent interfaces.

These are abstract contracts only — no implementations. Phase 3 will plug in:
- `PlaywrightAgent` for headful/headless browser automation
- A LLM-backed `CompanyResearchAgent`
- An interactive `TelegramAgent` that pairs notifications with action shortcuts

We define the contracts here so Phase 2B code can be written against them and
Phase 3 only has to fill in the bodies.
"""
from __future__ import annotations

from jobforge.agents_phase3.browser import BrowserAgent, NavigationResult, PlaywrightAgent
from jobforge.agents_phase3.company_research import CompanyResearchAgent
from jobforge.agents_phase3.playwright_browser import (
    BrowserUnavailable,
    PlaywrightChromiumAgent,
)
from jobforge.agents_phase3.telegram_agent import TelegramAgent

__all__ = [
    "BrowserAgent",
    "BrowserUnavailable",
    "CompanyResearchAgent",
    "NavigationResult",
    "PlaywrightAgent",
    "PlaywrightChromiumAgent",
    "TelegramAgent",
]
