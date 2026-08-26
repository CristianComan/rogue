"""Runtime configuration for the ROGUE control-plane API.

Values are sourced from environment variables (see docker-compose.yml,
which sets the ROGUE_* variables consumed here).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide settings, loaded once at import time."""

    model_config = SettingsConfigDict(env_prefix="ROGUE_", extra="ignore")

    database_url: str = "postgresql+psycopg://rogue:rogue_dev_only@localhost:5432/rogue"
    nats_url: str = "nats://localhost:4222"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "rogue"
    s3_access_key: str = "rogue"
    s3_secret_key: str = "rogue_dev_password"
    # M3's Vite dev server origin. Comma-separated for other environments,
    # e.g. ROGUE_CORS_ALLOWED_ORIGINS="http://localhost:5173,https://lab.example".
    cors_allowed_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
