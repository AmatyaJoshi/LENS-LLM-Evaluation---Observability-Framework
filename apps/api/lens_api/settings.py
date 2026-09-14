"""Runtime settings (env prefix ``LENS_``)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from lens_core.env import load_dotenv


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LENS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    api_key: str | None = None  # when set, ingest + API require X-Lens-API-Key / Bearer
    api_keys: str = ""  # extra comma-separated keys accepted alongside api_key (key rotation)

    # request guards
    max_request_bytes: int = 32 * 1024 * 1024  # reject bodies larger than this (413)
    rate_limit_rpm: int = 0  # per-key/IP requests per minute; 0 disables

    # span store
    span_store: Literal["clickhouse", "memory", "sqlite"] = "clickhouse"
    sqlite_span_path: str = "lens_spans.db"
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

    # online evaluation sampling (SPEC.md §5.4)
    eval_dispatch: Literal["off", "inline", "celery"] = "off"
    eval_sample_rate: float = 0.1  # fraction of ok traces to score
    eval_on_error: bool = True  # always score traces containing an error span
    eval_on_negative_feedback: bool = (
        True  # always score traces with lens.user.feedback < 0 / thumbs down
    )
    eval_metrics: str = "faithfulness,answer_relevance,hallucination,safety"
    eval_judge_tier: str = "frontier"

    # live injection detection (SPEC.md §6.5)
    detector_enabled: bool = True
    detector_threshold: float = 0.5

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, v: object) -> object:
        # docker compose passes LENS_API_KEY="" when unset; treat blank as "auth disabled".
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def valid_keys(self) -> set[str]:
        keys = {self.api_key} if self.api_key else set()
        keys |= {k.strip() for k in self.api_keys.split(",") if k.strip()}
        return keys

    def auth_enabled(self) -> bool:
        return bool(self.valid_keys())

    def redaction_enabled(self, app: str) -> bool:
        if not self.redact_apps:
            return False
        if self.redact_apps.strip() == "*":
            return True
        return app in {a.strip() for a in self.redact_apps.split(",") if a.strip()}


@lru_cache
def get_settings() -> Settings:
    load_dotenv()  # make OPENROUTER_API_KEY / LENS_JUDGE_* visible to LiteLLM and the router
    return Settings()
