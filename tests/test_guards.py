"""API request guards: multi-key auth, body-size cap, rate limiting."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient

from lens_api.main import create_app
from lens_api.settings import Settings, get_settings


def _client(**overrides: object) -> Iterator[TestClient]:
    settings = Settings(span_store="memory", env="test", postgres_dsn="sqlite://", **overrides)  # type: ignore[arg-type]
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


def test_multi_key_auth() -> None:
    (c,) = list(_client(api_key="primary", api_keys="rotated1, rotated2"))
    assert c.get("/traces").status_code == 401
    assert c.get("/traces", headers={"x-lens-api-key": "primary"}).status_code == 200
    assert c.get("/traces", headers={"x-lens-api-key": "rotated2"}).status_code == 200
    assert c.get("/traces", headers={"authorization": "Bearer rotated1"}).status_code == 200
    assert c.get("/traces", headers={"x-lens-api-key": "nope"}).status_code == 401


def test_body_size_limit() -> None:
    (c,) = list(_client(max_request_bytes=1000))
    big = "x" * 2000
    r = c.post("/v1/traces", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_rate_limit() -> None:
    (c,) = list(_client(rate_limit_rpm=3))
    codes = [c.get("/traces").status_code for _ in range(6)]
    assert codes.count(200) == 3 and codes.count(429) == 3
    # /health is never limited
    assert c.get("/health").status_code == 200
