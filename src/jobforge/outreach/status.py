"""Outreach campaign status flow.

Forward path:  drafted → sent → replied → interview → closed.
`ignored` is a terminal-ish branch from `sent` when no response materialises.
`closed` is the only true terminal — everything else can be reopened by
sending a fresh message.

Transitions are advisory rather than enforced. Unusual jumps get
event_type=`status_change_unusual` instead of being blocked — this matches
the Phase 2B applications/status.py posture.
"""
from __future__ import annotations

STATUS_DRAFTED = "drafted"
STATUS_SENT = "sent"
STATUS_REPLIED = "replied"
STATUS_IGNORED = "ignored"
STATUS_INTERVIEW = "interview"
STATUS_CLOSED = "closed"

ALL_STATUSES = (
    STATUS_DRAFTED,
    STATUS_SENT,
    STATUS_REPLIED,
    STATUS_IGNORED,
    STATUS_INTERVIEW,
    STATUS_CLOSED,
)

TERMINAL_STATUSES = frozenset({STATUS_CLOSED})

_ALLOWED_FORWARD: dict[str, frozenset[str]] = {
    STATUS_DRAFTED: frozenset({STATUS_SENT, STATUS_CLOSED}),
    STATUS_SENT: frozenset({STATUS_REPLIED, STATUS_IGNORED, STATUS_INTERVIEW, STATUS_CLOSED}),
    STATUS_REPLIED: frozenset({STATUS_INTERVIEW, STATUS_CLOSED}),
    STATUS_IGNORED: frozenset({STATUS_SENT, STATUS_REPLIED, STATUS_CLOSED}),
    STATUS_INTERVIEW: frozenset({STATUS_CLOSED}),
}


def is_valid_status(status: str) -> bool:
    return status in ALL_STATUSES


def is_forward_transition(from_status: str, to_status: str) -> bool:
    allowed = _ALLOWED_FORWARD.get(from_status, frozenset())
    return to_status in allowed


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
