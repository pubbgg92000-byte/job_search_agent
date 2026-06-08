"""Application status flow.

Status values follow the PRD. Transitions are advisory rather than enforced —
we record every change as an `application_events` row so the audit trail
stays honest even for unusual jumps (e.g. Saved → Offer, when the user is
forwarded a role they didn't formally apply to).
"""
from __future__ import annotations

# Single canonical capitalization. Stored lowercased for sortability.
STATUS_SAVED = "saved"
STATUS_TAILORED = "tailored"
STATUS_APPLIED = "applied"
STATUS_INTERVIEW_SCHEDULED = "interview_scheduled"
STATUS_INTERVIEW_COMPLETED = "interview_completed"
STATUS_REJECTED = "rejected"
STATUS_OFFER = "offer"
STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"

ALL_STATUSES = (
    STATUS_SAVED,
    STATUS_TAILORED,
    STATUS_APPLIED,
    STATUS_INTERVIEW_SCHEDULED,
    STATUS_INTERVIEW_COMPLETED,
    STATUS_REJECTED,
    STATUS_OFFER,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
)

TERMINAL_STATUSES = frozenset({STATUS_REJECTED, STATUS_ACCEPTED, STATUS_DECLINED})

# Allowed forward transitions. Backwards/exotic transitions are allowed but
# flagged with event_type="status_change_unusual" so analytics can spot them.
_ALLOWED_FORWARD: dict[str, frozenset[str]] = {
    STATUS_SAVED: frozenset({STATUS_TAILORED, STATUS_APPLIED, STATUS_REJECTED}),
    STATUS_TAILORED: frozenset({STATUS_APPLIED, STATUS_REJECTED}),
    STATUS_APPLIED: frozenset(
        {STATUS_INTERVIEW_SCHEDULED, STATUS_REJECTED, STATUS_OFFER}
    ),
    STATUS_INTERVIEW_SCHEDULED: frozenset(
        {STATUS_INTERVIEW_COMPLETED, STATUS_REJECTED}
    ),
    STATUS_INTERVIEW_COMPLETED: frozenset(
        {STATUS_OFFER, STATUS_REJECTED, STATUS_INTERVIEW_SCHEDULED}
    ),
    STATUS_OFFER: frozenset({STATUS_ACCEPTED, STATUS_DECLINED, STATUS_REJECTED}),
}


def is_valid_status(status: str) -> bool:
    return status in ALL_STATUSES


def is_forward_transition(from_status: str, to_status: str) -> bool:
    """Whether the transition is on the expected forward path."""
    allowed = _ALLOWED_FORWARD.get(from_status, frozenset())
    return to_status in allowed


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
