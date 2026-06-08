from __future__ import annotations

import pytest
from pydantic import ValidationError

from jobforge import config


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    config._settings = None
    yield
    config._settings = None


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/x")
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    # Avoid loading the dev .env from the repo root during tests.
    monkeypatch.chdir(tmp_path)

    settings = config.get_settings()
    assert settings.anthropic_api_key == "sk-test"
    assert settings.model_default == "claude-sonnet-4-6"
    assert settings.model_tailoring == "claude-opus-4-8"
    assert settings.artifacts_dir.exists()


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        config.get_settings()
