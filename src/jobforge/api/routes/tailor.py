from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from jobforge.db.models import Profile
from jobforge.db.session import session_scope
from jobforge.pipelines.tailor_for_jd import DailyRunLimitExceeded, tailor_for_jd

router = APIRouter()


class TailorRequest(BaseModel):
    profile_id: int = Field(..., gt=0)
    jd_text: str = Field(..., min_length=10)
    company_name: str | None = None
    url: str | None = None


@router.post("/")
async def run_tailor(req: TailorRequest) -> dict[str, Any]:
    async with session_scope() as session:
        result = await session.execute(select(Profile.id).where(Profile.id == req.profile_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail=f"profile_id={req.profile_id} not found")

    try:
        out = await tailor_for_jd(
            profile_id=req.profile_id,
            jd_text=req.jd_text,
            company_name=req.company_name,
            url=req.url,
        )
    except DailyRunLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {
        "artifact_id": out.artifact_id,
        "job_id": out.job_id,
        "profile_id": out.profile_id,
        "company": out.company,
        "title": out.title,
        "score_before": out.score_before,
        "score_after": out.score_after,
        "missing_keywords": out.missing_keywords,
        "tailored_resume_md": out.tailored_resume_md,
        "cover_letter_md": out.cover_letter_md,
    }
