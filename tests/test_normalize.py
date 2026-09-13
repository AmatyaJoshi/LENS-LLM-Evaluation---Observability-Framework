from __future__ import annotations

import base64
import json

import pytest
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from lens_api.ingest import normalize, semconv
from lens_api.ingest.redact import regex_redact
from tests.conftest import load_fixture


def _to_proto_bytes(payload: dict) -> bytes:
    # OTLP/JSON uses hex ids; protobuf-JSON mapping wants base64 for bytes fields.
    def fix(span: dict) -> None:
        for key in ("traceId", "spanId", "parentSpanId"):
            if key in span:
                span[key] = base64.b64encode(bytes.fromhex(span[key])).decode()

    for rs in payload["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                fix(s)
    return ParseDict(payload, ExportTraceServiceRequest()).SerializeToString()


def test_protobuf_and_json_decode_identically() -> None:
    payload = load_fixture("otel_genai")
    from_json = normalize.otlp_json_to_spans(payload)
    from_proto = normalize.otlp_proto_to_spans(_to_proto_bytes(json.loads(json.dumps(payload))))
    assert [s.model_dump() for s in from_proto] == [s.model_dump() for s in from_json]


def test_ids_accept_hex_and_base64() -> None:
    hex_id = "0af7651916cd43dd8448eb211c80319c"
    b64 = base64.b64encode(bytes.fromhex(hex_id)).decode()
    assert normalize._decode_id(hex_id, 32) == hex_id
    assert normalize._decode_id(hex_id.upper(), 32) == hex_id
    assert normalize._decode_id(b64, 32) == hex_id
    assert normalize._decode_id("", 32) is None


def test_attribute_truncation_flag() -> None:
    big = "x" * 70_000
    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "0" * 32,
                                "spanId": "1" * 16,
                                "name": "s",
                                "startTimeUnixNano": "1",
                                "endTimeUnixNano": "2",
                                "attributes": [
                                    {"key": "big", "value": {"stringValue": big}},
                                    {"key": "small", "value": {"stringValue": "ok"}},
                                    {"key": "n", "value": {"intValue": "7"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    (span,) = normalize.otlp_json_to_spans(payload, max_attribute_bytes=64 * 1024)
    assert span.truncated_attributes == ["big"]
    assert span.attributes["big"].endswith(normalize.TRUNCATION_SUFFIX)
    assert len(span.attributes["big"]) < 70_000
    assert span.attributes["small"] == "ok"
    assert span.attributes["n"] == 7
    assert span.kind == "other"


def test_error_status_and_events() -> None:
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "0" * 32,
                                "spanId": "1" * 16,
                                "name": "s",
                                "startTimeUnixNano": "1",
                                "endTimeUnixNano": "2",
                                "status": {"code": "STATUS_CODE_ERROR", "message": "boom"},
                                "attributes": [
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "t"}}
                                ],
                                "events": [
                                    {
                                        "name": "exception",
                                        "timeUnixNano": "2",
                                        "attributes": [
                                            {
                                                "key": "exception.type",
                                                "value": {"stringValue": "ValueError"},
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    (span,) = normalize.otlp_json_to_spans(payload)
    assert span.status == "error" and span.status_message == "boom"
    assert span.kind == "tool"
    assert span.events[0].attributes["exception.type"] == "ValueError"
    tool = normalize.derive_tool_call(span)
    assert tool.error == "boom" and tool.name == "t"


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"gen_ai.operation.name": "chat"}, "llm"),
        ({"gen_ai.operation.name": "text_completion"}, "llm"),
        ({"gen_ai.operation.name": "embeddings"}, "embedding"),
        ({"gen_ai.operation.name": "execute_tool"}, "tool"),
        ({"gen_ai.operation.name": "invoke_agent"}, "agent_step"),
        ({"llm.request.type": "chat"}, "llm"),
        ({"llm.request.type": "embedding"}, "embedding"),
        ({"traceloop.span.kind": "workflow"}, "agent_step"),
        ({"traceloop.span.kind": "agent"}, "agent_step"),
        ({"traceloop.span.kind": "tool"}, "tool"),
        ({"traceloop.span.kind": "task"}, "chain"),
        ({"traceloop.span.kind": "task", "lens.retrieval.query": "q"}, "retrieval"),
        ({"db.system": "vector"}, "retrieval"),
        ({"gen_ai.tool.name": "x"}, "tool"),
        ({"gen_ai.system": "openai", "gen_ai.request.model": "m"}, "llm"),
        ({"http.method": "GET"}, "other"),
    ],
)
def test_detect_kind(attributes: dict, expected: str) -> None:
    assert semconv.detect_kind(attributes) == expected


def test_indexed_attribute_grouping() -> None:
    attrs = {
        "gen_ai.prompt.0.role": "system",
        "gen_ai.prompt.0.content": "s",
        "gen_ai.prompt.1.role": "user",
        "gen_ai.prompt.1.content": "u",
        "gen_ai.prompt": "not-indexed",
    }
    msgs = semconv.messages_in(attrs, [])
    assert [(m.role, m.content) for m in msgs] == [("system", "s"), ("user", "u")]


def test_legacy_function_call_completion() -> None:
    attrs = {
        "llm.completions.0.role": "assistant",
        "llm.completions.0.function_call.name": "f",
        "llm.completions.0.function_call.arguments": '{"a": 1}',
    }
    msg, _ = semconv.message_out(attrs, [])
    assert msg is not None
    assert msg.tool_calls[0].name == "f" and msg.tool_calls[0].arguments == {"a": 1}


def test_per_role_event_messages() -> None:
    events = [
        {"name": "gen_ai.user.message", "attributes": {"content": "hi"}},
        {"name": "gen_ai.tool.message", "attributes": {"content": "42", "id": "c9"}},
        {
            "name": "gen_ai.choice",
            "attributes": {
                "finish_reason": "stop",
                "index": 0,
                "message": '{"role":"assistant","content":"yo"}',
            },
        },
    ]
    msgs = semconv.messages_in({}, events)
    assert [(m.role, m.content, m.tool_call_id) for m in msgs] == [
        ("user", "hi", None),
        ("tool", "42", "c9"),
    ]
    out, fin = semconv.message_out({}, events)
    assert out is not None and out.content == "yo" and fin == "stop"


def test_regex_redaction() -> None:
    text = "mail jane.doe@example.com or call 415-555-0134, card 4111 1111 1111 1111"
    red = regex_redact(text)
    assert "example.com" not in red and "<EMAIL>" in red
    assert "<PHONE>" in red and "<CREDIT_CARD>" in red
