"""API-level tests that don't require a live Anthropic key.

The /health endpoint and the validation/error paths of /tailor and /profile are
fully deterministic. Pipeline-success paths are out of scope here (they need a
cassette).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from jobforge.api.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_schema_generates_and_lists_routes() -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/profile/" in paths
    assert "/tailor/" in paths
    assert "/health" in paths


def test_tailor_validation_rejects_short_jd() -> None:
    r = client.post("/tailor/", json={"profile_id": 1, "jd_text": "short"})
    assert r.status_code == 422
    body = r.json()
    assert any("jd_text" in err["loc"] for err in body["detail"])


def test_tailor_validation_rejects_zero_profile_id() -> None:
    r = client.post(
        "/tailor/",
        json={"profile_id": 0, "jd_text": "a sufficiently long jd text"},
    )
    assert r.status_code == 422
    body = r.json()
    assert any("profile_id" in err["loc"] for err in body["detail"])


def test_profile_rejects_non_pdf() -> None:
    files = {"file": ("notes.txt", b"hello", "text/plain")}
    r = client.post("/profile/", files=files)
    assert r.status_code == 400
    assert "pdf" in r.json()["detail"].lower()


def test_profile_rejects_oversize_pdf() -> None:
    # Use a fake .pdf filename so we reach the size check (not the MIME check).
    from jobforge.api.routes.profile import MAX_RESUME_BYTES

    payload = b"%PDF-1.4\n" + b"x" * (MAX_RESUME_BYTES + 1)
    files = {"file": ("big.pdf", payload, "application/pdf")}
    r = client.post("/profile/", files=files)
    assert r.status_code == 413
    assert "limit" in r.json()["detail"].lower()


def test_profile_rejects_malformed_pdf() -> None:
    files = {"file": ("garbage.pdf", b"not actually a pdf", "application/pdf")}
    r = client.post("/profile/", files=files)
    assert r.status_code == 400
    assert "pdf" in r.json()["detail"].lower()
