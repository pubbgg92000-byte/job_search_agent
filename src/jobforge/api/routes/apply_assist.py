"""Apply-assist HTTP surface, mounted under /applications.

Endpoints:
    POST  /{application_id}/apply-assist/start
    GET   /{application_id}/apply-assist/sessions/{session_id}
    POST  /{application_id}/apply-assist/sessions/{session_id}/approve
    POST  /{application_id}/apply-assist/sessions/{session_id}/cancel
    GET   /{application_id}/apply-assist/sessions/{session_id}/screenshot/{idx}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jobforge.applications.apply_assist import (
    ApplyAssistError,
    approve,
    cancel,
    get_session,
    list_events_for_session,
    serialize_session,
    start_session,
)
from jobforge.applications.status import STATUS_APPLIED
from jobforge.config import get_settings

router = APIRouter()


class StartPayload(BaseModel):
    profile_id: int | None = Field(default=None, ge=1)
    resume_path: str | None = None
    cover_letter_path: str | None = None


def _event_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "notes": e.notes,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
    }


async def _envelope(session_id: int) -> dict[str, Any]:
    s = get_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    events = await list_events_for_session(s)
    return {
        "session": serialize_session(s),
        "events": [_event_dict(e) for e in events],
    }


@router.post("/{application_id}/apply-assist/start")
async def post_start(application_id: int, payload: StartPayload) -> dict[str, Any]:
    try:
        s = await start_session(
            application_id,
            profile_id=payload.profile_id,
            resume_path=payload.resume_path,
            cover_letter_path=payload.cover_letter_path,
        )
    except ApplyAssistError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        if "too many" in msg.lower():
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return await _envelope(s.id)


@router.get("/{application_id}/apply-assist/sessions/{session_id}")
async def get_session_route(application_id: int, session_id: int) -> dict[str, Any]:
    s = get_session(session_id)
    if s is None or s.application_id != application_id:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return await _envelope(session_id)


@router.post("/{application_id}/apply-assist/sessions/{session_id}/approve")
async def post_approve(application_id: int, session_id: int) -> dict[str, Any]:
    s = get_session(session_id)
    if s is None or s.application_id != application_id:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    try:
        await approve(session_id)
    except ApplyAssistError as exc:
        msg = str(exc).lower()
        if "expected" in msg or "ready" in msg:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    body = await _envelope(session_id)
    body["application_status"] = STATUS_APPLIED
    return body


@router.post("/{application_id}/apply-assist/sessions/{session_id}/cancel")
async def post_cancel(application_id: int, session_id: int) -> dict[str, Any]:
    s = get_session(session_id)
    if s is None or s.application_id != application_id:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    try:
        await cancel(session_id)
    except ApplyAssistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _envelope(session_id)


@router.get("/{application_id}/apply-assist/sessions/{session_id}/screenshot/{idx}")
async def get_screenshot(application_id: int, session_id: int, idx: int) -> FileResponse:
    s = get_session(session_id)
    if s is None or s.application_id != application_id:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if idx < 0 or idx >= len(s.screenshot_paths):
        raise HTTPException(status_code=404, detail=f"screenshot {idx} out of range")
    raw = s.screenshot_paths[idx]
    path = Path(raw).resolve()
    settings = get_settings()
    root = settings.apply_assist_screenshot_dir.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        # Defence-in-depth against a polluted registry entry pointing outside
        # the screenshot dir.
        raise HTTPException(status_code=403, detail="screenshot outside allowed dir") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="screenshot file missing on disk")
    return FileResponse(str(path), media_type="image/png")
