"""GET/PUT /preferences — user preferences for ranking."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from jobforge.config import get_settings
from jobforge.preferences import PreferencesDTO, load_preferences, upsert_preferences

router = APIRouter()


class PreferencesPayload(BaseModel):
    preferred_locations: list[str] = Field(default_factory=list)
    remote_only: bool = True
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)

    def to_dto(self) -> PreferencesDTO:
        return PreferencesDTO(
            preferred_locations=self.preferred_locations,
            remote_only=self.remote_only,
            salary_min=self.salary_min,
            salary_max=self.salary_max,
            salary_currency=self.salary_currency,
            preferred_roles=self.preferred_roles,
            preferred_skills=self.preferred_skills,
            excluded_companies=self.excluded_companies,
            excluded_keywords=self.excluded_keywords,
        )


@router.get("")
@router.get("/")
async def get_preferences() -> dict:
    settings = get_settings()
    dto = await load_preferences(settings.sole_user_id)
    return dto.to_dict()


@router.put("")
@router.put("/")
async def put_preferences(payload: PreferencesPayload) -> dict:
    settings = get_settings()
    dto = await upsert_preferences(settings.sole_user_id, payload.to_dto())
    return dto.to_dict()
