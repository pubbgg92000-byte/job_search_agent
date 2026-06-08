"""User preferences — load / upsert + adapter to the match engine's `UserPreferences`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobforge.db.models import UserPreferences as UserPreferencesRow
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger
from jobforge.match import UserPreferences as MatchPreferences

log = get_logger("jobforge.preferences")


@dataclass
class PreferencesDTO:
    preferred_locations: list[str]
    remote_only: bool
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    preferred_roles: list[str]
    preferred_skills: list[str]
    excluded_companies: list[str]
    excluded_keywords: list[str]

    @classmethod
    def from_row(cls, row: UserPreferencesRow) -> PreferencesDTO:
        return cls(
            preferred_locations=list(row.preferred_locations or []),
            remote_only=row.remote_only,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
            preferred_roles=list(row.preferred_roles or []),
            preferred_skills=list(row.preferred_skills or []),
            excluded_companies=list(row.excluded_companies or []),
            excluded_keywords=list(row.excluded_keywords or []),
        )

    @classmethod
    def defaults(cls) -> PreferencesDTO:
        """Permissive defaults — used when a user has never set preferences."""
        return cls(
            preferred_locations=[],
            remote_only=True,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            preferred_roles=[],
            preferred_skills=[],
            excluded_companies=[],
            excluded_keywords=[],
        )

    def to_match_preferences(self) -> MatchPreferences:
        return MatchPreferences(
            seniority=None,  # inferred from profile, not user-set
            locations=tuple(self.preferred_locations),
            prefers_remote=self.remote_only or len(self.preferred_locations) == 0,
            salary_min_required=self.salary_min,
            salary_currency=self.salary_currency,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_locations": self.preferred_locations,
            "remote_only": self.remote_only,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "preferred_roles": self.preferred_roles,
            "preferred_skills": self.preferred_skills,
            "excluded_companies": self.excluded_companies,
            "excluded_keywords": self.excluded_keywords,
        }


async def _load_row(session: AsyncSession, user_id: int) -> UserPreferencesRow | None:
    result = await session.execute(
        select(UserPreferencesRow).where(UserPreferencesRow.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def load_preferences(user_id: int) -> PreferencesDTO:
    """Return the user's stored preferences, or defaults if none exist."""
    async with session_scope() as session:
        row = await _load_row(session, user_id)
        if row is None:
            return PreferencesDTO.defaults()
        return PreferencesDTO.from_row(row)


async def upsert_preferences(user_id: int, dto: PreferencesDTO) -> PreferencesDTO:
    """Create or update the user's preferences row. Idempotent on user_id."""
    async with session_scope() as session:
        row = await _load_row(session, user_id)
        if row is None:
            row = UserPreferencesRow(user_id=user_id)
            session.add(row)
        for field, value in dto.to_dict().items():
            setattr(row, field, value)
        await session.flush()
        log.info(
            "preferences.upsert",
            extra={
                "user_id": user_id,
                "remote_only": dto.remote_only,
                "locations": len(dto.preferred_locations),
                "excluded_companies": len(dto.excluded_companies),
            },
        )
        return PreferencesDTO.from_row(row)


def apply_exclusions(prefs: PreferencesDTO, job: dict[str, Any]) -> bool:
    """Return True if the job should be EXCLUDED based on prefs.

    Used by the ranking layer to filter results before scoring.
    """
    company = (job.get("company") or "").lower()
    if any(company == ex.lower() or ex.lower() in company for ex in prefs.excluded_companies if ex):
        return True
    blob = " ".join(
        [(job.get("title") or ""), (job.get("description") or "")]
    ).lower()
    return any(kw and kw.lower() in blob for kw in prefs.excluded_keywords)
