"""AI Assistant: grounded fallback (no key) and cassette-backed grounded answers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lens_api.main import create_app
from lens_api.settings import Settings, get_settings
from tests.conftest import load_fixture

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def _client(monkeypatch: pytest.MonkeyPatch, cassette: Path | None) -> TestClient:
    if cassette:
        monkeypatch.setenv("LENS_JUDGE_CASSETTE", str(cassette))
    else:
        monkeypatch.delenv("LENS_JUDGE_CASSETTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(span_store="memory", env="test", api_key=None, postgres_dsn="sqlite://")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_capabilities_reports_ungrounded_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, None) as c:
        caps = c.get("/assistant/capabilities").json()
    assert caps["grounded_answers"] is False and "ANTHROPIC_API_KEY" in caps["note"]


def test_fallback_answer_returns_raw_context_never_fabricates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(monkeypatch, None) as c:
        c.post("/v1/traces", json=load_fixture("openllmetry_python"))
        r = c.post(
            "/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "what happened in this trace?"}],
                "focus": "trace",
                "trace_id": TRACE_ID,
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is False
    # the fallback answer is built only from real Lens data, never invented
    assert body["context_summary"]["trace_id"] == TRACE_ID
    assert body["context_summary"]["app"] == "rag_demo"
    assert "rag_demo" in body["answer"]
    assert body["suggestions"]


def test_grounded_answer_with_cassette(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cassette = tmp_path / "assistant.json"
    # The assistant calls judge._complete directly (bare prompt name ""), so script under the
    # empty prompt-name key used by CassetteJudge for un-hashed lookups.
    cassette.write_text(
        json.dumps({"entries": {"": ["You have 1 trace in the last 24h with a 0% error rate."]}}),
        encoding="utf-8",
    )
    with _client(monkeypatch, cassette) as c:
        c.post("/v1/traces", json=load_fixture("openllmetry_python"))
        r = c.post(
            "/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "summarise my traffic"}],
                "focus": "overview",
            },
        )
    body = r.json()
    assert body["grounded"] is True
    assert "1 trace" in body["answer"]
    assert body["model"] == "cassette"


def test_trace_focus_context(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, None) as c:
        c.post("/v1/traces", json=load_fixture("openllmetry_python"))
        r = c.post(
            "/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "is this trace safe?"}],
                "focus": "trace",
                "trace_id": TRACE_ID,
            },
        )
    ctx = r.json()["context_summary"]
    assert ctx["trace_id"] == TRACE_ID and ctx["app"] == "rag_demo"
    assert ctx["tool_calls"] == ["lookup_policy"]
    assert "Explain the injection flagged in this trace" not in r.json()["suggestions"]
