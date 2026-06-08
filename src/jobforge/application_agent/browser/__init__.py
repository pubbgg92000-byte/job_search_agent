"""Browser-driven application agent (Phase 3B)."""
from __future__ import annotations

from jobforge.application_agent.browser.events import (
    ALL_EVENT_TYPES,
    EVENT_CANCELLED,
    EVENT_FAILED,
    EVENT_FORM_COMPLETED,
    EVENT_FORM_STARTED,
    EVENT_READY_FOR_REVIEW,
    EVENT_SUBMITTED,
)
from jobforge.application_agent.browser.runner import (
    PlaywrightApplicationAgent,
    RunnerError,
)
from jobforge.application_agent.browser.selectors import (
    FILLABLE_FIELDS_ORDER,
    SelectorSpec,
    selector_for,
    selectors_for,
    supported_platforms,
)
from jobforge.application_agent.browser.session import (
    ACTIVE_STATES,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_IN_PROGRESS,
    STATE_READY_FOR_REVIEW,
    STATE_SUBMITTED,
    TERMINAL_STATES,
    ApplyAssistSession,
    RegistryError,
    SessionRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    "ACTIVE_STATES",
    "ALL_EVENT_TYPES",
    "EVENT_CANCELLED",
    "EVENT_FAILED",
    "EVENT_FORM_COMPLETED",
    "EVENT_FORM_STARTED",
    "EVENT_READY_FOR_REVIEW",
    "EVENT_SUBMITTED",
    "FILLABLE_FIELDS_ORDER",
    "STATE_CANCELLED",
    "STATE_FAILED",
    "STATE_IN_PROGRESS",
    "STATE_READY_FOR_REVIEW",
    "STATE_SUBMITTED",
    "TERMINAL_STATES",
    "ApplyAssistSession",
    "PlaywrightApplicationAgent",
    "RegistryError",
    "RunnerError",
    "SelectorSpec",
    "SessionRegistry",
    "get_registry",
    "reset_registry",
    "selector_for",
    "selectors_for",
    "supported_platforms",
]
