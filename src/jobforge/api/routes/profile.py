from __future__ import annotations

import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from jobforge.agents.resume_parser import parse_resume_pdf
from jobforge.config import get_settings
from jobforge.db.models import Profile, User
from jobforge.db.session import session_scope

router = APIRouter()

MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB — generous for a resume PDF
_READ_CHUNK = 64 * 1024


async def _ensure_user() -> int:
    settings = get_settings()
    async with session_scope() as session:
        result = await session.execute(select(User).where(User.id == settings.sole_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=settings.sole_user_id,
                name=settings.sole_user_name,
                email=settings.sole_user_email,
                telegram_chat_id=settings.telegram_chat_id,
            )
            session.add(user)
            await session.flush()
        return user.id


@router.post("/")
async def upload_profile(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf is accepted in MVP")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            total = 0
            while chunk := await file.read(_READ_CHUNK):
                total += len(chunk)
                if total > MAX_RESUME_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Resume exceeds {MAX_RESUME_BYTES // (1024 * 1024)} MB limit",
                    )
                tmp.write(chunk)

        try:
            raw_text, parsed = await parse_resume_pdf(tmp_path)
        except fitz.FileDataError as exc:
            raise HTTPException(
                status_code=400, detail="File is not a valid PDF"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Only hit the DB once we know the upload is good.
        user_id = await _ensure_user()

        async with session_scope() as session:
            profile = Profile(
                user_id=user_id,
                source_filename=file.filename,
                raw_resume_text=raw_text,
                parsed_json=parsed,
            )
            session.add(profile)
            await session.flush()
            return {
                "profile_id": profile.id,
                "name": parsed.get("name"),
                "skills_count": len(parsed.get("skills", [])),
                "experience_count": len(parsed.get("experience", [])),
            }
    finally:
        if tmp_path is not None:
            with suppress(FileNotFoundError):
                tmp_path.unlink()
