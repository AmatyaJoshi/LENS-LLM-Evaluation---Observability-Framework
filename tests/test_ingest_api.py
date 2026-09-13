from __future__ import annotations

import gzip
import json

from fastapi.testclient import TestClient

from lens_api.main import create_app
from lens_api.settings import Settings, get_settings
from tests.conftest import load_fixture

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["span_store"] == "memory"


def test_ingest_json_then_read_trajectory(client: TestClient) -> None:
    r = client.post("/v1/traces", json=load_fixture("openllmetry_python"))
    assert r.status_code == 200, r.text
    assert r.json() == {"partialSuccess": {}}

    traces = client.get("/traces").json()
    assert len(traces) == 1
    assert traces[0]["trace_id"] == TRACE_ID
    assert traces[0]["app"] == "rag_demo"
    assert traces[0]["span_count"] == 5 and traces[0]["llm_calls"] == 2

    spans = client.get(f"/traces/{TRACE_ID}").json()
    assert len(spans) == 5

    traj = client.get(f"/traces/{TRACE_ID}/trajectory").json()
    assert traj["app"] == "rag_demo" and len(traj["steps"]) == 2
    assert traj["final_output"].startswith("Acme Pro purchases")

    assert client.get(f"/traces/{'f' * 32}/trajectory").status_code == 404
    assert client.get("/traces", params={"app": "nope"}).json() == []


def test_ingest_gzip_json(client: TestClient) -> None:
    body = gzip.compress(json.dumps(load_fixture("lens_sdk")).encode())
    r = client.post(
        "/v1/traces",
        content=body,
        headers={"content-type": "application/json", "content-encoding": "gzip"},
    )
    assert r.status_code == 200
    assert len(client.get(f"/traces/{TRACE_ID}").json()) == 5


def test_ingest_protobuf(client: TestClient) -> None:
    from tests.test_normalize import _to_proto_bytes

    body = _to_proto_bytes(load_fixture("otel_genai"))
    r = client.post("/v1/traces", content=body, headers={"content-type": "application/x-protobuf"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-protobuf"
    assert len(client.get(f"/traces/{TRACE_ID}").json()) == 5


def test_malformed_payload_is_400(client: TestClient) -> None:
    r = client.post(
        "/v1/traces", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert r.status_code == 400


def test_websocket_receives_trace_notification(client: TestClient) -> None:
    with client.websocket_connect("/ws/traces") as ws:
        client.post("/v1/traces", json=load_fixture("openllmetry_ts"))
        msg = ws.receive_json()
    assert msg == {"type": "trace", "trace_id": TRACE_ID, "app": "rag_demo", "spans": 5}


def test_api_key_enforced_when_configured() -> None:
    settings = Settings(span_store="memory", env="test", api_key="secret")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        assert c.post("/v1/traces", json={}).status_code == 401
        assert c.get("/traces").status_code == 401
        ok = c.post("/v1/traces", json={}, headers={"x-lens-api-key": "secret"})
        assert ok.status_code == 200
        ok2 = c.get("/traces", headers={"authorization": "Bearer secret"})
        assert ok2.status_code == 200


def test_redaction_applied_per_app() -> None:
    settings = Settings(span_store="memory", env="test", redact_apps="rag_demo")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    payload = load_fixture("lens_sdk")
    root = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    root["attributes"].append(
        {"key": "lens.user.feedback", "value": {"stringValue": "email me at a@b.io"}}
    )
    with TestClient(app) as c:
        assert c.post("/v1/traces", json=payload).status_code == 200
        traj = c.get(f"/traces/{TRACE_ID}/trajectory").json()
    assert traj["metadata"]["lens.user.feedback"] == "email me at <EMAIL>"
