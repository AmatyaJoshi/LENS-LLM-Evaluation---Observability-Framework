"""Lens Python SDK (SPEC.md §9).

A thin wrapper over OpenTelemetry that emits the OTel GenAI + Lens attributes Lens normalises
(SPEC.md §4). When ``traceloop-sdk`` is installed, ``init()`` also turns on OpenLLMetry's
auto-instrumentation so existing OpenAI/Anthropic/LangChain/vector-store calls are captured
without code changes; the Lens helpers below add the ``lens.*`` attributes on top.

    import lens_sdk as lens

    lens.init(app="rag_demo", endpoint="http://localhost:4318")

    @lens.trace(kind="agent_step", name="answer")
    def answer(q: str) -> str:
        docs = retrieve(q)
        lens.log_retrieval(q, docs)          # docs: list[dict|str] or (id, text, score)
        out = call_llm(q, docs)
        return out

    lens.feedback(trace_id, thumbs="down", comment="wrong refund window")
    lens.expected(trace_id, "Acme Pro: 30 days")
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import trace as _trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

__version__ = "0.1.0"
__all__ = [
    "init",
    "trace",
    "span",
    "log_retrieval",
    "feedback",
    "expected",
    "set_session",
    "set_run",
]

_F = TypeVar("_F", bound=Callable[..., Any])

_KIND_ATTRS: dict[str, dict[str, str]] = {
    "agent_step": {"traceloop.span.kind": "agent"},
    "workflow": {"traceloop.span.kind": "workflow"},
    "chain": {"traceloop.span.kind": "task"},
    "tool": {"gen_ai.operation.name": "execute_tool"},
    "retrieval": {"traceloop.span.kind": "task"},
    "llm": {"gen_ai.operation.name": "chat"},
}

_initialized = False


def init(
    app: str,
    endpoint: str | None = None,
    api_key: str | None = None,
    *,
    use_traceloop: bool | None = None,
    resource_attributes: dict[str, str] | None = None,
) -> None:
    """Initialise tracing for ``app``. Idempotent.

    ``endpoint`` defaults to ``OTEL_EXPORTER_OTLP_ENDPOINT`` or ``http://localhost:4318``.
    If ``traceloop-sdk`` is installed (and ``use_traceloop`` is not False), OpenLLMetry
    auto-instrumentation is enabled; otherwise a plain OTLP/HTTP exporter is configured.
    """
    global _initialized
    if _initialized:
        return
    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    headers = {"x-lens-api-key": api_key} if api_key else {}

    want_traceloop = use_traceloop if use_traceloop is not None else True
    if want_traceloop:
        try:
            from traceloop.sdk import Traceloop

            Traceloop.init(
                app_name=app,
                api_endpoint=endpoint,
                headers=headers or None,
                disable_batch=False,
            )
            _initialized = True
            return
        except ImportError:
            pass  # fall back to plain OTel

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": app, **(resource_attributes or {})})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", headers=headers or None)
        )
    )
    _trace.set_tracer_provider(provider)
    _initialized = True


def _tracer() -> _trace.Tracer:
    return _trace.get_tracer("lens-sdk", __version__)


def _current() -> Span:
    return _trace.get_current_span()


@contextmanager
def span(name: str, *, kind: str = "chain", attributes: dict[str, Any] | None = None):
    """Context manager creating a Lens-tagged span."""
    with _tracer().start_as_current_span(name) as s:
        s.set_attribute("traceloop.entity.name", name)
        for k, v in _KIND_ATTRS.get(kind, {}).items():
            s.set_attribute(k, v)
        for k, v in (attributes or {}).items():
            s.set_attribute(
                k, v if isinstance(v, str | int | float | bool) else json.dumps(v, default=str)
            )
        yield s


def trace(kind: str = "chain", name: str | None = None) -> Callable[[_F], _F]:
    """Decorator wrapping a function in a Lens-tagged span (SPEC.md §9 ``@lens.trace``)."""

    def decorator(fn: _F) -> _F:
        span_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, kind=kind) as s:
                s.set_attribute(
                    "traceloop.entity.input",
                    json.dumps({"args": _safe(args), "kwargs": _safe(kwargs)}),
                )
                result = fn(*args, **kwargs)
                s.set_attribute("traceloop.entity.output", json.dumps(_safe(result)))
                return result

        return wrapper  # type: ignore[return-value]

    return decorator


def log_retrieval(query: str, documents: Sequence[Any], *, span_name: str = "retrieve") -> None:
    """Record a retrieval on a child span (SPEC.md §4 ``lens.retrieval.*``).

    ``documents`` may be strings, dicts ({id?, text, score?}), or (id, text, score) tuples.
    """
    docs: list[dict[str, Any]] = []
    for i, d in enumerate(documents):
        if isinstance(d, str):
            docs.append({"id": None, "text": d, "score": None, "rank": i + 1})
        elif isinstance(d, dict):
            docs.append(
                {
                    "id": d.get("id"),
                    "text": d.get("text") or d.get("content") or d.get("page_content") or "",
                    "score": d.get("score"),
                    "rank": d.get("rank", i + 1),
                }
            )
        elif isinstance(d, tuple | list) and len(d) >= 2:
            docs.append(
                {"id": d[0], "text": d[1], "score": d[2] if len(d) > 2 else None, "rank": i + 1}
            )
    with span(span_name, kind="retrieval") as s:
        s.set_attribute("lens.retrieval.query", query)
        s.set_attribute("lens.retrieval.docs", json.dumps(docs, default=str))


def feedback(
    trace_id: str | None = None,
    *,
    thumbs: str | None = None,
    score: float | None = None,
    comment: str | None = None,
) -> None:
    """Attach user feedback to the current span (SPEC.md §4 ``lens.user.feedback``)."""
    value: Any = score
    if value is None and thumbs is not None:
        value = 1 if thumbs.lower() in ("up", "thumbs_up", "positive", "1") else -1
    s = _current()
    if value is not None:
        s.set_attribute("lens.user.feedback", value)
    if comment:
        s.set_attribute("lens.user.feedback.comment", comment)
    if trace_id:
        s.set_attribute("lens.feedback.trace_id", trace_id)


def expected(trace_id: str | None = None, expected_output: str = "") -> None:
    """Attach an expected output for offline evaluation (SPEC.md §4 ``lens.eval.expected_output``)."""
    s = _current()
    s.set_attribute("lens.eval.expected_output", expected_output)
    if trace_id:
        s.set_attribute("lens.eval.trace_id", trace_id)


def set_session(session_id: str) -> None:
    _current().set_attribute("lens.session.id", session_id)


def set_run(run_id: str) -> None:
    _current().set_attribute("lens.run.id", run_id)


def _safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
