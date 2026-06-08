"""Tests for user preferences storage + match-engine adapter."""
from __future__ import annotations

from sqlalchemy import delete

from jobforge.db.models import User, UserPreferences
from jobforge.db.session import session_scope
from jobforge.match import UserPreferences as MatchPreferences
from jobforge.preferences import (
    PreferencesDTO,
    apply_exclusions,
    load_preferences,
    upsert_preferences,
)


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        existing = await session.get(User, user_id)
        if existing is None:
            session.add(User(id=user_id, name="Prefs Test", email=f"prefs-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            delete(UserPreferences).where(UserPreferences.user_id == user_id)
        )


async def test_defaults_when_no_row_present() -> None:
    user_id = 70001
    await _ensure_user(user_id)
    await _wipe(user_id)
    dto = await load_preferences(user_id)
    assert dto == PreferencesDTO.defaults()
    assert dto.remote_only is True
    assert dto.preferred_locations == []
    assert dto.salary_min is None


async def test_upsert_inserts_then_updates() -> None:
    user_id = 70002
    await _ensure_user(user_id)
    await _wipe(user_id)

    dto1 = PreferencesDTO(
        preferred_locations=["Bengaluru"],
        remote_only=False,
        salary_min=120000,
        salary_max=200000,
        salary_currency="USD",
        preferred_roles=["Backend"],
        preferred_skills=["Python"],
        excluded_companies=["BoringCo"],
        excluded_keywords=["crypto"],
    )
    saved1 = await upsert_preferences(user_id, dto1)
    assert saved1.salary_min == 120000
    assert saved1.preferred_locations == ["Bengaluru"]

    dto2 = PreferencesDTO(
        preferred_locations=["Berlin"],
        remote_only=True,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        preferred_roles=[],
        preferred_skills=[],
        excluded_companies=[],
        excluded_keywords=[],
    )
    saved2 = await upsert_preferences(user_id, dto2)
    assert saved2.preferred_locations == ["Berlin"]
    assert saved2.salary_min is None  # cleared correctly


async def test_to_match_preferences_passes_locations_and_salary() -> None:
    dto = PreferencesDTO(
        preferred_locations=["Bengaluru", "Mumbai"],
        remote_only=False,
        salary_min=120000,
        salary_max=200000,
        salary_currency="USD",
        preferred_roles=[],
        preferred_skills=[],
        excluded_companies=[],
        excluded_keywords=[],
    )
    mp = dto.to_match_preferences()
    assert isinstance(mp, MatchPreferences)
    assert mp.locations == ("Bengaluru", "Mumbai")
    assert mp.salary_min_required == 120000
    assert mp.prefers_remote is False  # explicit


async def test_to_match_preferences_defaults_remote_when_no_locations() -> None:
    dto = PreferencesDTO.defaults()
    mp = dto.to_match_preferences()
    assert mp.prefers_remote is True


async def test_apply_exclusions_filters_blocked_companies() -> None:
    dto = PreferencesDTO(
        preferred_locations=[],
        remote_only=True,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        preferred_roles=[],
        preferred_skills=[],
        excluded_companies=["BoringCo"],
        excluded_keywords=[],
    )
    assert apply_exclusions(dto, {"company": "BoringCo", "title": "X", "description": ""}) is True
    # Substring match
    assert apply_exclusions(dto, {"company": "BoringCo Inc", "title": "X", "description": ""}) is True
    # Different company passes through
    assert apply_exclusions(dto, {"company": "Acme", "title": "X", "description": ""}) is False


async def test_apply_exclusions_filters_blocked_keywords_in_title_or_description() -> None:
    dto = PreferencesDTO(
        preferred_locations=[],
        remote_only=True,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        preferred_roles=[],
        preferred_skills=[],
        excluded_companies=[],
        excluded_keywords=["crypto", "blockchain"],
    )
    assert apply_exclusions(dto, {"company": "Acme", "title": "Crypto Engineer", "description": "x"}) is True
    assert apply_exclusions(dto, {"company": "Acme", "title": "Engineer", "description": "Blockchain work"}) is True
    assert apply_exclusions(dto, {"company": "Acme", "title": "Engineer", "description": "Python"}) is False
