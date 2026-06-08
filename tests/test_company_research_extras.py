"""Phase 3B: extra coverage around the API route, merging, and signal serialization."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from jobforge.api.main import app
from jobforge.company import (
    CompanyEnrichmentData,
    CompanyIntelligenceService,
    CompanySignal,
    EnrichmentProvider,
)
from jobforge.company.base import merge_enrichment_data
from jobforge.company.service import _RAW_SIGNALS_KEY, _serialize_phase3b
from jobforge.config import get_settings
from jobforge.db.models import CompanyProfile
from jobforge.db.session import session_scope


async def _wipe(name: str) -> None:
    async with session_scope() as session:
        await session.execute(delete(CompanyProfile).where(CompanyProfile.name == name))


def _sync_url() -> str:
    return get_settings().database_url.replace("+asyncpg", "+psycopg")


_sync_engine = None
_SyncSession: sessionmaker[Session] | None = None


def _get_sync_session() -> sessionmaker[Session]:
    global _sync_engine, _SyncSession
    if _SyncSession is None:
        _sync_engine = create_engine(_sync_url(), future=True)
        _SyncSession = sessionmaker(_sync_engine, expire_on_commit=False)
    return _SyncSession


@pytest.fixture
def sync_db() -> Iterator[Session]:
    SS = _get_sync_session()
    s = SS()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# --------------------------- merge -----------------------------------------


def test_merge_unions_tech_stacks_dedup() -> None:
    a = CompanyEnrichmentData(name="A", tech_stack=["python", "rust"])
    b = CompanyEnrichmentData(name="A", tech_stack=["rust", "kafka"])
    merged = merge_enrichment_data(a, b)
    assert merged.tech_stack == ["python", "rust", "kafka"]


def test_merge_concatenates_news_items_in_order() -> None:
    a = CompanyEnrichmentData(
        name="A",
        news_items=[{"title": "older", "summary": "", "url": None, "published_at": None, "category": "news"}],
    )
    b = CompanyEnrichmentData(
        name="A",
        news_items=[{"title": "newer", "summary": "", "url": None, "published_at": None, "category": "news"}],
    )
    merged = merge_enrichment_data(a, b)
    titles = [n["title"] for n in merged.news_items]
    assert titles == ["older", "newer"]


def test_merge_preserves_existing_velocity_when_new_is_none() -> None:
    a = CompanyEnrichmentData(name="A", hiring_velocity_score=50)
    b = CompanyEnrichmentData(name="A")
    merged = merge_enrichment_data(a, b)
    assert merged.hiring_velocity_score == 50


def test_merge_prefers_new_velocity_when_set() -> None:
    a = CompanyEnrichmentData(name="A", hiring_velocity_score=50)
    b = CompanyEnrichmentData(name="A", hiring_velocity_score=85)
    merged = merge_enrichment_data(a, b)
    assert merged.hiring_velocity_score == 85


def test_merge_unions_signals_list() -> None:
    a = CompanyEnrichmentData(
        name="A",
        signals=[CompanySignal(kind="funding", value="seed", source="x")],
    )
    b = CompanyEnrichmentData(
        name="A",
        signals=[CompanySignal(kind="news", value={"title": "Hi"}, source="y")],
    )
    merged = merge_enrichment_data(a, b)
    assert len(merged.signals) == 2


def test_merge_keeps_layoffs_true_when_either_side_true() -> None:
    a = CompanyEnrichmentData(name="A", layoffs_detected=True)
    b = CompanyEnrichmentData(name="A")  # None
    merged = merge_enrichment_data(a, b)
    assert merged.layoffs_detected is True


# --------------------------- signal serialization --------------------------


def test_company_signal_to_dict_round_trip() -> None:
    sig = CompanySignal(
        kind="funding",
        value="series_b",
        source="manual",
        confidence=70,
        notes="seeded by admin",
        observed_at=datetime(2026, 6, 8, tzinfo=UTC),
    )
    payload = sig.to_dict()
    assert payload["kind"] == "funding"
    assert payload["value"] == "series_b"
    assert payload["observed_at"] == "2026-06-08T00:00:00+00:00"


def test_phase3b_serialization_packs_all_fields() -> None:
    data = CompanyEnrichmentData(
        name="A",
        hiring_velocity_score=80,
        open_roles_count=42,
        tech_stack=["python"],
        layoffs_detected=False,
        signals=[CompanySignal(kind="funding", value="seed", source="x")],
    )
    payload = _serialize_phase3b(data, confidence=66)
    assert payload["confidence_score"] == 66
    assert payload["hiring_velocity_score"] == 80
    assert payload["open_roles_count"] == 42
    assert payload["tech_stack"] == ["python"]
    assert len(payload["signals"]) == 1


# --------------------------- API route -------------------------------------


def _seed_company_profile(session: Session, name: str, *, phase3b_payload: dict) -> None:
    session.execute(delete(CompanyProfile).where(CompanyProfile.name == name))
    session.add(
        CompanyProfile(
            name=name,
            industry="fintech",
            company_size="51-200",
            funding_stage="series_b",
            growth_score=65,
            risk_score=22,
            summary=None,
            apply_recommendation=True,
            raw_signals={_RAW_SIGNALS_KEY: phase3b_payload},
            last_updated_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_api_company_get_includes_phase3b_fields(
    sync_db: Session, client: TestClient
) -> None:
    """Sync seed a fully-populated profile and read it back through the API.

    Uses the same fixture pattern as Phase 2A's `test_api_jobs` to avoid
    cross-loop asyncpg issues. The profile is within the 7-day TTL, so the
    API returns the cached row without running any provider.
    """
    payload = {
        "confidence_score": 78,
        "hiring_velocity_score": 65,
        "open_roles_count": 22,
        "tech_stack": ["python", "kafka"],
        "layoffs_detected": False,
        "engineering_team_signals": {"has_engineering_blog": True},
        "glassdoor_signals": {},
        "news_items": [
            {
                "title": "RouteCo raises $30M",
                "summary": "Series B",
                "url": "https://news.test/1",
                "published_at": "2026-06-01T00:00:00Z",
                "category": "funding",
            }
        ],
        "signals": [
            {
                "kind": "funding",
                "value": "series_b",
                "source": "route_stub",
                "confidence": 70,
                "notes": None,
                "observed_at": None,
            }
        ],
    }
    _seed_company_profile(sync_db, "RouteCo", phase3b_payload=payload)

    response = client.get("/companies/RouteCo")
    assert response.status_code == 200
    body = response.json()

    # Phase 2B keys still present and unchanged
    assert body["name"] == "RouteCo"
    assert body["industry"] == "fintech"
    assert body["growth_score"] == 65
    assert body["risk_score"] == 22

    # Phase 3B additions
    assert body["hiring_velocity_score"] == 65
    assert body["open_roles_count"] == 22
    assert "python" in body["tech_stack"]
    assert body["confidence_score"] == 78
    assert isinstance(body["signals"], list) and len(body["signals"]) == 1
    assert body["news_items"][0]["category"] == "funding"


def test_api_company_get_phase3b_defaults_when_no_phase3b_payload(
    sync_db: Session, client: TestClient
) -> None:
    """Seed a legacy-shaped row (no Phase 3B in raw_signals) and confirm safe defaults."""
    sync_db.execute(delete(CompanyProfile).where(CompanyProfile.name == "LegacyCo"))
    sync_db.add(
        CompanyProfile(
            name="LegacyCo",
            industry="fintech",
            growth_score=50,
            risk_score=30,
            apply_recommendation=True,
            raw_signals=None,
            last_updated_at=datetime.now(UTC),
        )
    )
    sync_db.commit()

    response = client.get("/companies/LegacyCo")
    body = response.json()
    assert body["tech_stack"] == []
    assert body["news_items"] == []
    assert body["confidence_score"] is None
    assert body["hiring_velocity_score"] is None


# --------------------------- TTL semantics ---------------------------------


async def test_service_cache_expires_after_seven_days() -> None:
    await _wipe("TtlCo")

    class _Stub(EnrichmentProvider):
        name = "stub"

        def __init__(self) -> None:
            self.calls = 0

        async def enrich(
            self,
            company_name: str,
            *,
            hints: CompanyEnrichmentData | None = None,
        ) -> CompanyEnrichmentData:
            self.calls += 1
            return CompanyEnrichmentData(
                name=company_name, industry="fintech", company_size="51-200"
            )

    stub = _Stub()
    service = CompanyIntelligenceService(providers=[stub])
    await service.enrich("TtlCo")
    # 6 days later — still cached
    snap = await service.get_cached(
        "TtlCo", now=datetime.now(UTC) + timedelta(days=6)
    )
    assert snap is not None
    # 8 days later — expired
    snap = await service.get_cached(
        "TtlCo", now=datetime.now(UTC) + timedelta(days=8)
    )
    assert snap is None
