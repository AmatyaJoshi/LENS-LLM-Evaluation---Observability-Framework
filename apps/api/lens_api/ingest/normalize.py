"""OTLP → normalised Lens spans → derived views (SPEC.md §3.1, §4).

Two decoders (``otlp_json_to_spans`` for OTLP/JSON and ``otlp_proto_to_spans``
for OTLP/protobuf) funnel into one code path via the protobuf JSON mapping, so
both wire formats are guaranteed to normalise identically.

Rules enforced here (SPEC.md §4):
* unknown attributes are never dropped (``Span.attributes`` keeps everything);
* string attributes above ``max_attribute_bytes`` are truncated and the key is
  recorded in ``Span.truncated_attributes``;
* kind detection and all field mapping go through ``semconv``.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable, Mapping
from typing import Any

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from lens_api.ingest import semconv
from lens_core import pricing
from lens_core.trace.model import (
    LLMCall,
    Retrieval,
    RetrievedDoc,
    Span,
    SpanEvent,
    ToolCall,
)
from lens_core.trace.trajectory import DerivedSpans

TRUNCATION_SUFFIX = "…[truncated]"


# ---------------------------------------------------------------------------------------------
# OTLP decoding
# ---------------------------------------------------------------------------------------------


def _decode_id(value: Any, length: int) -> str | None:
    """OTLP/JSON encodes ids as hex; protobuf-JSON encodes them as base64. Accept both."""
    if not value:
        return None
    if isinstance(value, bytes):
        return value.hex()
    s = str(value)
    if len(s) == length and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.lower()
    try:
        raw = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        return s.lower()
    return raw.hex()


def _any_value(v: Any) -> Any:
    """Decode an OTLP ``AnyValue`` (JSON form) into a plain Python value."""
    if not isinstance(v, Mapping):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "bytesValue" in v:
        return v["bytesValue"]
    if "arrayValue" in v:
        return [_any_value(x) for x in (v["arrayValue"] or {}).get("values", [])]
    if "kvlistValue" in v:
        return _attributes((v["kvlistValue"] or {}).get("values", []))
    return None


def _attributes(kvs: Iterable[Mapping[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in kvs or []:
        key = kv.get("key")
        if key is not None:
            out[str(key)] = _any_value(kv.get("value"))
    return out


def _status(raw: Mapping[str, Any] | None) -> tuple[str, str | None]:
    if not raw:
        return "ok", None
    code = raw.get("code")
    is_error = code in (2, "2", "STATUS_CODE_ERROR")
    return ("error" if is_error else "ok"), (raw.get("message") or None)


def _ns(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _truncate(attributes: dict[str, Any], max_bytes: int) -> list[str]:
    truncated: list[str] = []
    for key, value in attributes.items():
        if isinstance(value, str) and len(value.encode("utf-8")) > max_bytes:
            cut = value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
            attributes[key] = cut + TRUNCATION_SUFFIX
            truncated.append(key)
    return truncated


def otlp_json_to_spans(
    payload: Mapping[str, Any], *, max_attribute_bytes: int = 64 * 1024
) -> list[Span]:
    """Decode an OTLP/JSON ``ExportTraceServiceRequest`` into normalised spans."""
    spans: list[Span] = []
    for rs in payload.get("resourceSpans") or payload.get("resource_spans") or []:
        resource = _attributes((rs.get("resource") or {}).get("attributes"))
        scope_spans = rs.get("scopeSpans") or rs.get("scope_spans") or []
        for ss in scope_spans:
            scope = ss.get("scope") or {}
            for raw in ss.get("spans") or []:
                trace_id = _decode_id(raw.get("traceId") or raw.get("trace_id"), 32)
                span_id = _decode_id(raw.get("spanId") or raw.get("span_id"), 16)
                if not trace_id or not span_id:
                    continue
                attributes = _attributes(raw.get("attributes"))
                if scope.get("name"):
                    attributes.setdefault("otel.scope.name", scope["name"])
                truncated = _truncate(attributes, max_attribute_bytes)
                status, status_message = _status(raw.get("status"))
                events = [
                    SpanEvent(
                        name=str(ev.get("name", "")),
                        time_ns=_ns(ev.get("timeUnixNano") or ev.get("time_unix_nano")),
                        attributes=_attributes(ev.get("attributes")),
                    )
                    for ev in raw.get("events") or []
                ]
                spans.append(
                    Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=_decode_id(
                            raw.get("parentSpanId") or raw.get("parent_span_id"), 16
                        ),
                        name=str(raw.get("name") or "unnamed"),
                        kind=semconv.detect_kind(attributes),
                        start_ns=_ns(
                            raw.get("startTimeUnixNano") or raw.get("start_time_unix_nano")
                        ),
                        end_ns=_ns(raw.get("endTimeUnixNano") or raw.get("end_time_unix_nano")),
                        status=status,  # type: ignore[arg-type]
                        status_message=status_message,
                        attributes=attributes,
                        resource=resource,
                        events=events,
                        truncated_attributes=truncated,
                    )
                )
    return spans


def otlp_proto_to_spans(body: bytes, *, max_attribute_bytes: int = 64 * 1024) -> list[Span]:
    """Decode an OTLP/protobuf ``ExportTraceServiceRequest`` into normalised spans."""
    req = ExportTraceServiceRequest()
    req.ParseFromString(body)
    payload = MessageToDict(req, preserving_proto_field_name=False)
    return otlp_json_to_spans(payload, max_attribute_bytes=max_attribute_bytes)


# ---------------------------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------------------------


def _events_as_dicts(span: Span) -> list[dict[str, Any]]:
    return [{"name": e.name, "attributes": e.attributes} for e in span.events]


def derive_llm_call(span: Span) -> LLMCall:
    attrs = span.attributes
    events = _events_as_dicts(span)
    msg_out, fin = semconv.message_out(attrs, events)
    tokens_in, tokens_out = semconv.tokens(attrs)
    prompt_version = attrs.get(semconv.LENS_PROMPT_VERSION)
    return LLMCall(
        span_id=span.span_id,
        provider=semconv.provider(attrs),
        model=semconv.model(attrs),
        messages_in=semconv.messages_in(attrs, events),
        message_out=msg_out,
        tool_calls=list(msg_out.tool_calls) if msg_out else [],
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=pricing.cost(semconv.model(attrs), tokens_in, tokens_out),
        temperature=semconv.temperature(attrs),
        prompt_version=str(prompt_version) if prompt_version is not None else None,
        finish_reason=fin,
        error=span.status_message if span.status == "error" else None,
        duration_ms=span.duration_ms,
    )


def derive_tool_call(span: Span) -> ToolCall:
    name, call_id, args, result = semconv.tool_fields(span.attributes, span.name)
    return ToolCall(
        span_id=span.span_id,
        name=name,
        call_id=call_id,
        args=args,
        result=result,
        error=span.status_message if span.status == "error" else None,
        duration_ms=span.duration_ms,
    )


def derive_retrieval(span: Span) -> Retrieval:
    query, docs = semconv.retrieval_fields(span.attributes)
    documents = [
        RetrievedDoc(
            text=str(d.get("text") or d.get("content") or d.get("page_content") or ""),
            id=str(d["id"]) if d.get("id") is not None else None,
            score=semconv.as_float(d.get("score")),
            rank=int(d.get("rank") or i + 1),
        )
        for i, d in enumerate(docs)
    ]
    return Retrieval(
        span_id=span.span_id, query=query, documents=documents, duration_ms=span.duration_ms
    )


def derive(spans: Iterable[Span]) -> DerivedSpans:
    derived = DerivedSpans()
    for span in spans:
        if span.kind == "llm":
            derived.llm_calls[span.span_id] = derive_llm_call(span)
        elif span.kind == "tool":
            derived.tool_calls[span.span_id] = derive_tool_call(span)
        elif span.kind == "retrieval":
            derived.retrievals[span.span_id] = derive_retrieval(span)
    return derived


def app_of(span: Span, default: str = "unknown") -> str:
    value = span.resource.get(semconv.SERVICE_NAME)
    return str(value) if value else default
