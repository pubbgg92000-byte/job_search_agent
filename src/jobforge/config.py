from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(..., description="Anthropic API key")
    database_url: str = Field(
        "postgresql+asyncpg://jobforge:jobforge@localhost:5434/jobforge",
        description="Async Postgres URL",
    )

    sole_user_id: int = 1
    sole_user_name: str = "Rahul"
    sole_user_email: str = "rahul@example.com"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    model_default: str = "claude-sonnet-4-6"
    model_tailoring: str = "claude-opus-4-8"

    artifacts_dir: Path = Path("./artifacts")
    max_runs_per_day: int = 50

    # Phase 3B: external research endpoints. Both optional; unset disables
    # the corresponding provider rather than throwing.
    company_research_endpoint: str | None = None
    company_news_endpoint: str | None = None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
        _settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return _settings
