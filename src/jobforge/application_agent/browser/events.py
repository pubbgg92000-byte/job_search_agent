"""ApplicationEvent.event_type constants for the apply-assist subsystem.

All values are prefixed `apply_assist.` so analytics queries that already
filter on `created` / `status_change` / `status_change_unusual` are not
disturbed by the new rows.
"""
from __future__ import annotations

EVENT_FORM_STARTED = "apply_assist.form_started"
EVENT_FORM_COMPLETED = "apply_assist.form_completed"
EVENT_READY_FOR_REVIEW = "apply_assist.ready_for_review"
EVENT_SUBMITTED = "apply_assist.submitted"
EVENT_FAILED = "apply_assist.failed"
EVENT_CANCELLED = "apply_assist.cancelled"

ALL_EVENT_TYPES = (
    EVENT_FORM_STARTED,
    EVENT_FORM_COMPLETED,
    EVENT_READY_FOR_REVIEW,
    EVENT_SUBMITTED,
    EVENT_FAILED,
    EVENT_CANCELLED,
)
