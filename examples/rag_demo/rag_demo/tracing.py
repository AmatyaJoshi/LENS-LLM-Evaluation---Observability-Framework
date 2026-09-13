"""Minimal OpenTelemetry setup for the RAG demo, emitting OTel GenAI + Lens attributes
that Lens normalises (SPEC.md §4). Kept dependency-light and framework-agnostic so the
example doubles as a copy-paste reference for instrumenting your own app.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span as OtelSpan

_KIND_ATTR = {
    "workflow": {"traceloop.span.kind": "workflow"},
    "task": {"traceloop.span.kind": "task"},
    "agent": {"traceloop.span.kind": "agent"},
    "tool": {"gen_ai.operation.name": "execute_tool"},
    "llm": {"gen_ai.operation.name": "chat"},
}


def init_tracing(app: FastAPI, service_name: str = "rag_demo") -> None:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(provider)


class SpanHandle:
    def __init__(self, otel_span: OtelSpan, name: str) -> None:
        self._span = otel_span
        self.name = name

    @property
    def trace_id(self) -> str:
        return format(self._span.get_span_context().trace_id, "032x")

    def set_retrieval(self, query: str, docs: list[tuple[str, str, float]]) -> None:
        self._span.set_attribute("lens.retrieval.query", query)
        self._span.set_attribute(
            "lens.retrieval.docs",
            json.dumps(
                [
                    {"id": i, "text": t, "score": s, "rank": r + 1}
                    for r, (i, t, s) in enumerate(docs)
                ]
            ),
        )

    def set_llm(self, system: str, user: str, output: str) -> None:
        self._span.set_attribute("gen_ai.system", "openai")
        self._span.set_attribute(
            "gen_ai.request.model", os.environ.get("RAG_DEMO_MODEL", "rule-based")
        )
        self._span.set_attribute("gen_ai.prompt.0.role", "system")
        self._span.set_attribute("gen_ai.prompt.0.content", system)
        self._span.set_attribute("gen_ai.prompt.1.role", "user")
        self._span.set_attribute("gen_ai.prompt.1.content", user)
        self._span.set_attribute("gen_ai.completion.0.role", "assistant")
        self._span.set_attribute("gen_ai.completion.0.content", output)
        self._span.set_attribute("gen_ai.usage.input_tokens", len(system + user) // 4)
        self._span.set_attribute("gen_ai.usage.output_tokens", max(1, len(output) // 4))

    def set_output(self, output: str) -> None:
        self._span.set_attribute("traceloop.entity.output", json.dumps(output))


@contextmanager
def span(name: str, *, kind: str = "task", entity_input: dict[str, Any] | None = None):
    tracer = trace.get_tracer("rag_demo")
    with tracer.start_as_current_span(name) as otel_span:
        otel_span.set_attribute("traceloop.entity.name", name.split(".")[0])
        for k, v in _KIND_ATTR.get(kind, {}).items():
            otel_span.set_attribute(k, v)
        if entity_input is not None:
            otel_span.set_attribute(
                "traceloop.entity.input", json.dumps({"args": [], "kwargs": entity_input})
            )
        yield SpanHandle(otel_span, name)
