"""Provider + contact-service tests for the outreach discovery layer."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from jobforge.db.models import RecruiterContact, User
from jobforge.db.session import session_scope
from jobforge.outreach import (
    OutreachError,
    UpsertContactRequest,
    contact_to_dict,
    delete_contact,
    discover_contacts,
    get_contact,
    list_contacts,
    upsert_contact,
)
from jobforge.outreach.providers import (
    DiscoveredContact,
    ManualProvider,
    WebResearchProvider,
)

USER_BASE = 90000


async def _ensure_user(user_id: int) -> None:
    async with session_scope() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id, name="Outreach", email=f"o-{user_id}@x.test"))


async def _wipe(user_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            delete(RecruiterContact).where(RecruiterContact.user_id == user_id)
        )


# ---------------- ManualProvider ----------------


async def test_manual_provider_returns_seeds() -> None:
    seeds = [DiscoveredContact(name="A", kind="recruiter")]
    out = await ManualProvider(seeds=seeds).discover("Acme")
    assert len(out) == 1
    assert out[0].source == "manual"


async def test_manual_provider_empty_when_no_seeds() -> None:
    out = await ManualProvider().discover("Acme")
    assert out == []


async def test_manual_provider_boosts_low_confidence_seeds() -> None:
    seeds = [DiscoveredContact(name="A", confidence=10)]
    out = await ManualProvider(seeds=seeds).discover("Acme")
    # Manual is human-verified — we floor to 75.
    assert out[0].confidence >= 75


# ---------------- WebResearchProvider ----------------


async def test_web_research_returns_empty_without_endpoint() -> None:
    out = await WebResearchProvider().discover("Acme")
    assert out == []


async def test_web_research_parses_response_when_endpoint_set(monkeypatch) -> None:
    monkeypatch.setattr(
        type(__import__("jobforge.config", fromlist=["get_settings"]).get_settings()),
        "outreach_research_endpoint",
        "https://research.test/contacts",
        raising=False,
    )

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {
                "contacts": [
                    {
                        "name": "Asha Mehta",
                        "kind": "talent_partner",
                        "role": "Senior Recruiter",
                        "linkedin_url": "https://linkedin.com/in/asha",
                        "confidence": 70,
                    },
                    {"name": "", "kind": "recruiter"},  # filtered
                    "not-a-dict",  # filtered
                ]
            }

    fake_post = AsyncMock(return_value=FakeResp())
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = fake_post
        out = await WebResearchProvider().discover("Acme")
    assert len(out) == 1
    assert out[0].name == "Asha Mehta"
    assert out[0].source == "web_research"


async def test_web_research_handles_http_error_gracefully(monkeypatch) -> None:
    monkeypatch.setattr(
        type(__import__("jobforge.config", fromlist=["get_settings"]).get_settings()),
        "outreach_research_endpoint",
        "https://research.test/contacts",
        raising=False,
    )

    class FakeResp:
        status_code = 503

        def json(self) -> dict:
            return {}

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=FakeResp())
        out = await WebResearchProvider().discover("Acme")
    assert out == []


async def test_web_research_handles_bad_json(monkeypatch) -> None:
    monkeypatch.setattr(
        type(__import__("jobforge.config", fromlist=["get_settings"]).get_settings()),
        "outreach_research_endpoint",
        "https://research.test/contacts",
        raising=False,
    )

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            raise ValueError("not json")

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=FakeResp())
        out = await WebResearchProvider().discover("Acme")
    assert out == []


# ---------------- upsert_contact ----------------


async def test_upsert_creates_then_updates_same_normalized_name() -> None:
    user_id = USER_BASE + 1
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="Sam Tan"),
    )
    b = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="sam tan", role="Senior Recruiter"),
    )
    assert a.id == b.id
    assert b.role == "Senior Recruiter"


async def test_upsert_widens_confidence_never_drops() -> None:
    user_id = USER_BASE + 2
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="Sam", confidence=80),
    )
    b = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="Sam", confidence=20),
    )
    assert a.id == b.id
    assert b.confidence == 80


async def test_upsert_prefers_non_manual_source_for_traceability() -> None:
    user_id = USER_BASE + 3
    await _ensure_user(user_id)
    await _wipe(user_id)
    a = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="Sam", source="manual"),
    )
    b = await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="Sam", source="web_research"),
    )
    assert a.id == b.id
    assert b.source == "web_research"


async def test_upsert_rejects_missing_company() -> None:
    with pytest.raises(OutreachError):
        await upsert_contact(USER_BASE, UpsertContactRequest(company="", name="X"))


async def test_upsert_rejects_missing_name() -> None:
    with pytest.raises(OutreachError):
        await upsert_contact(USER_BASE, UpsertContactRequest(company="Acme", name=""))


async def test_upsert_rejects_invalid_kind() -> None:
    with pytest.raises(OutreachError):
        await upsert_contact(
            USER_BASE,
            UpsertContactRequest(company="Acme", name="Sam", kind="vp_marketing"),
        )


async def test_upsert_rejects_invalid_confidence() -> None:
    with pytest.raises(OutreachError):
        await upsert_contact(
            USER_BASE, UpsertContactRequest(company="Acme", name="Sam", confidence=200)
        )


# ---------------- list / get / delete ----------------


async def test_list_contacts_filters_by_kind() -> None:
    user_id = USER_BASE + 4
    await _ensure_user(user_id)
    await _wipe(user_id)
    await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="R1", kind="recruiter")
    )
    await upsert_contact(
        user_id,
        UpsertContactRequest(company="Acme", name="HM1", kind="hiring_manager"),
    )
    total, rows = await list_contacts(user_id, kind="hiring_manager")
    assert total == 1
    assert rows[0].name == "HM1"


async def test_list_contacts_filters_by_company() -> None:
    user_id = USER_BASE + 5
    await _ensure_user(user_id)
    await _wipe(user_id)
    await upsert_contact(user_id, UpsertContactRequest(company="Acme", name="A"))
    await upsert_contact(user_id, UpsertContactRequest(company="OtherCo", name="A"))
    total, rows = await list_contacts(user_id, company="Acme")
    assert total == 1
    assert rows[0].company == "Acme"


async def test_get_contact_returns_none_when_user_mismatch() -> None:
    user_a = USER_BASE + 6
    user_b = USER_BASE + 7
    await _ensure_user(user_a)
    await _ensure_user(user_b)
    await _wipe(user_a)
    await _wipe(user_b)
    a = await upsert_contact(user_a, UpsertContactRequest(company="Acme", name="A"))
    assert await get_contact(user_b, a.id) is None


async def test_delete_contact_returns_true_when_owned() -> None:
    user_id = USER_BASE + 8
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await upsert_contact(user_id, UpsertContactRequest(company="Acme", name="A"))
    assert await delete_contact(user_id, row.id) is True
    assert await get_contact(user_id, row.id) is None


async def test_delete_contact_returns_false_for_unknown() -> None:
    user_id = USER_BASE + 9
    await _ensure_user(user_id)
    assert await delete_contact(user_id, 999_999) is False


# ---------------- discover_contacts ----------------


async def test_discover_contacts_dedupes_across_providers() -> None:
    user_id = USER_BASE + 10
    await _ensure_user(user_id)
    await _wipe(user_id)
    seeds_a = [DiscoveredContact(name="Sam Tan", confidence=60)]
    seeds_b = [DiscoveredContact(name="sam tan", confidence=85, role="HM")]
    rows = await discover_contacts(
        user_id,
        "Acme",
        providers=[ManualProvider(seeds=seeds_a), ManualProvider(seeds=seeds_b)],
    )
    # One row only — and the higher-confidence one wins inside the dedupe.
    assert len(rows) == 1
    assert rows[0].name == "sam tan" or rows[0].name == "Sam Tan"


async def test_discover_contacts_skips_provider_error() -> None:
    user_id = USER_BASE + 11
    await _ensure_user(user_id)
    await _wipe(user_id)

    class Broken:
        name = "broken"

        async def discover(self, company, hints=None):
            raise RuntimeError("boom")

    rows = await discover_contacts(
        user_id,
        "Acme",
        providers=[
            Broken(),
            ManualProvider(seeds=[DiscoveredContact(name="Survivor")]),
        ],
    )
    assert len(rows) == 1
    assert rows[0].name == "Survivor"


async def test_discover_contacts_no_persist_returns_transient_rows() -> None:
    user_id = USER_BASE + 12
    await _ensure_user(user_id)
    await _wipe(user_id)
    rows = await discover_contacts(
        user_id,
        "Acme",
        providers=[ManualProvider(seeds=[DiscoveredContact(name="Ephemeral")])],
        persist=False,
    )
    assert len(rows) == 1
    assert rows[0].id is None
    total, _ = await list_contacts(user_id, company="Acme")
    assert total == 0


async def test_discover_contacts_requires_company() -> None:
    with pytest.raises(OutreachError):
        await discover_contacts(USER_BASE, "", providers=[ManualProvider()])


async def test_contact_to_dict_round_trips() -> None:
    user_id = USER_BASE + 13
    await _ensure_user(user_id)
    await _wipe(user_id)
    row = await upsert_contact(
        user_id, UpsertContactRequest(company="Acme", name="Sam")
    )
    d = contact_to_dict(row)
    expected = {
        "id",
        "user_id",
        "company",
        "name",
        "kind",
        "role",
        "linkedin_url",
        "email",
        "phone",
        "source",
        "confidence",
        "notes",
        "created_at",
        "last_updated_at",
    }
    assert set(d.keys()) == expected
