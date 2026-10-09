"""Runtime configuration.

Scope note: this prototype has no production secrets management — it
reads from environment variables / a local .env for a single-developer
demo. Do not treat this module as a model for production config handling.
"""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://tutorbuddy:tutorbuddy@localhost:5432/tutorbuddy"
    )
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    # When true (or when no API key is configured), the tutor loop never
    # calls the LLM provider and always uses the safe static templates.
    # AGENTS.md rule 6: no unsafe fallback provider — this is the safe
    # fallback, not a convenience toggle to be routed around.
    safe_mode_only: bool = False
    # Shared demo password (HTTP basic auth, any username). If unset, the
    # app is open -- fine locally, not for a public URL.
    demo_password: str | None = None

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Render/Heroku-style URLs use postgres:// or postgresql://
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


settings = Settings()
