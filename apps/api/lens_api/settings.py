"""Runtime settings (env prefix ``LENS_``)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LENS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    api_key: str | None = None  # when set, ingest + API require X-Lens-API-Key / Bearer

    # span store
    span_store: Literal["clickhouse", "memory"] = "clickhouse"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "lens"
    clickhouse_password: str = "lens"
    clickhouse_database: str = "lens"
    clickhouse_secure: bool = False

    # relational store
    postgres_dsn: str = "postgresql+psycopg://lens:lens@localhost:5432/lens"

    # queue
    redis_url: str = "redis://localhost:6379/0"

    # ingest rules (SPEC.md §4)
    max_attribute_bytes: int = 64 * 1024
    redact_apps: str = ""  # comma-separated app names, or "*" for all
    default_app: str = "unknown"

    def redaction_enabled(self, app: str) -> bool:
        if not self.redact_apps:
            return False
        if self.redact_apps.strip() == "*":
            return True
        return app in {a.strip() for a in self.redact_apps.split(",") if a.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
