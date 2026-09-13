from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lens_api.main import create_app
from lens_api.settings import Settings, get_settings

FIXTURES = Path(__file__).parent / "fixtures" / "otlp"
FIXTURE_NAMES = ("openllmetry_python", "openllmetry_ts", "otel_genai", "lens_sdk")


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def memory_settings() -> Settings:
    return Settings(span_store="memory", env="test", api_key=None, postgres_dsn="sqlite://")


@pytest.fixture
def client(memory_settings: Settings) -> Iterator[TestClient]:
    app = create_app(memory_settings)
    app.dependency_overrides[get_settings] = lambda: memory_settings
    with TestClient(app) as c:
        yield c
