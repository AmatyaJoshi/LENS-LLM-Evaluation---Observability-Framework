"""OTLP/HTTP ingest endpoint: ``POST /v1/traces`` (JSON or protobuf, optionally gzip).

Pipeline per batch: decode → normalise → redact (per app) → live injection
detection (SPEC.md §6.5, sets ``lens.security.*`` attributes) → store →
broadcast over WebSocket → online-evaluation sampling (SPEC.md §5.4).

gRPC ingest is provided by the OpenTelemetry Collector (apps/collector), which
receives OTLP/gRPC + OTLP/HTTP on 4317/4318 and forwards to this endpoint.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import random
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from lens_api.deps import get_store, require_api_key
from lens_api.ingest import normalize, semconv
from lens_api.ingest.redact import build_redactor, redact_span
from lens_api.models.clickhouse import SpanStore
from lens_api.settings import Settings, get_settings
from lens_api.ws import hub
from lens_core.redteam.detector import get_detector
from lens_core.trace.model import Span

log = logging.getLogger("lens.ingest")
router = APIRouter(tags=["ingest"])

_redactor = build_redactor()

ATTR_INJECTION_SCORE = "lens.security.injection_score"
ATTR_INJECTION_FLAGGED = "lens.security.flagged"
ATTR_DETECTOR = "lens.security.detector"
ATTR_INJECTION_REASONS = "lens.security.reasons"


def untrusted_texts(span: Span) -> list[str]:
    """Text segments an attacker could control: user/tool messages, retrieved docs, tool results."""
    texts: list[str] = []
    if span.kind == "llm":
        call = normalize.derive_llm_call(span)
        texts.extend(
            m.content for m in call.messages_in if m.role in ("user", "tool") and m.content
        )
    elif span.kind == "retrieval":
        texts.extend(d.text for d in normalize.derive_retrieval(span).documents if d.text)
    elif span.kind == "tool":
        result = normalize.derive_tool_call(span).result
        if result is not None:
            texts.append(result if isinstance(result, str) else json.dumps(result, default=str))
    return [t for t in texts if t]


def scan_spans(spans: list[Span], threshold: float) -> int:
    """Attach detector scores to spans in place; returns number of flagged spans."""
    detector = get_detector()
    flagged = 0
    for span in spans:
        texts = untrusted_texts(span)
        if not texts:
            continue
        results = detector.score_batch(texts)
        best = max(results, key=lambda r: r.score)
        span.attributes[ATTR_INJECTION_SCORE] = best.score
        span.attributes[ATTR_INJECTION_FLAGGED] = best.score >= threshold
        span.attributes[ATTR_DETECTOR] = f"{detector.name}@{detector.version}"
        if best.reasons:
            span.attributes[ATTR_INJECTION_REASONS] = ",".join(best.reasons[:5])
        if best.score >= threshold:
            flagged += 1
    return flagged


def should_sample(spans: list[Span], settings: Settings) -> str | None:
    """Return the sampling reason when a trace should be evaluated online, else None."""
    if settings.eval_on_error and any(s.status == "error" for s in spans):
        return "error"
    if settings.eval_on_negative_feedback:
        for s in spans:
            fb = s.attributes.get(semconv.LENS_USER_FEEDBACK)
            if isinstance(fb, int | float) and fb < 0:
                return "negative_feedback"
            if isinstance(fb, str) and fb.lower() in ("down", "thumbs_down", "negative", "-1"):
                return "negative_feedback"
    if any(s.attributes.get(ATTR_INJECTION_FLAGGED) for s in spans):
        return "injection_flagged"
    if settings.eval_sample_rate > 0 and random.random() < settings.eval_sample_rate:  # noqa: S311
        return "sampled"
    return None


def dispatch_evaluation(
    request: Request, store: SpanStore, settings: Settings, trace_id: str, reason: str
) -> None:
    metrics = [m.strip() for m in settings.eval_metrics.split(",") if m.strip()]
    if settings.eval_dispatch == "celery":
        try:
            from celery import Celery

            Celery(broker=settings.redis_url).send_task(
                "lens.evaluate_trace",
                args=[trace_id, metrics, settings.eval_judge_tier],
                queue="lens.eval",
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to enqueue evaluation for %s", trace_id)
        return
    if settings.eval_dispatch == "inline":
        from lens_api.services import evaluation as svc

        engine = request.app.state.db_engine

        async def _job() -> None:
            try:
                await svc.evaluate_trace(
                    trace_id,
                    store=store,
                    engine=engine,
                    judge=svc.judge_for(settings.eval_judge_tier),
                    metrics=metrics,
                    judge_tier=settings.eval_judge_tier,
                )
            except Exception:  # noqa: BLE001
                log.exception("inline evaluation failed for %s (%s)", trace_id, reason)

        asyncio.ensure_future(_job())


@router.post("/v1/traces", dependencies=[Depends(require_api_key)])
async def ingest_traces(
    request: Request,
    store: Annotated[SpanStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    content_type: Annotated[str | None, Header(alias="content-type")] = None,
    content_encoding: Annotated[str | None, Header(alias="content-encoding")] = None,
) -> Response:
    body = await request.body()
    if content_encoding and "gzip" in content_encoding.lower():
        body = gzip.decompress(body)

    ctype = (content_type or "").split(";")[0].strip().lower()
    try:
        if ctype == "application/x-protobuf":
            spans = normalize.otlp_proto_to_spans(
                body, max_attribute_bytes=settings.max_attribute_bytes
            )
        else:
            payload: dict[str, Any] = json.loads(body or b"{}")
            spans = normalize.otlp_json_to_spans(
                payload, max_attribute_bytes=settings.max_attribute_bytes
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"malformed OTLP payload: {exc}") from exc

    spans = [
        redact_span(s, _redactor) if settings.redaction_enabled(normalize.app_of(s)) else s
        for s in spans
    ]
    flagged = scan_spans(spans, settings.detector_threshold) if settings.detector_enabled else 0
    accepted = await store.insert_spans(spans)

    trace_ids = sorted({s.trace_id for s in spans})
    for tid in trace_ids:
        subset = [s for s in spans if s.trace_id == tid]
        await hub.broadcast(
            {
                "type": "trace",
                "trace_id": tid,
                "app": normalize.app_of(subset[0], settings.default_app),
                "spans": len(subset),
                "flagged": sum(1 for s in subset if s.attributes.get(ATTR_INJECTION_FLAGGED)),
            }
        )
        if settings.eval_dispatch != "off":
            reason = should_sample(subset, settings)
            if reason:
                dispatch_evaluation(request, store, settings, tid, reason)

    if flagged:
        log.info("live detector flagged %d span(s) in %d trace(s)", flagged, len(trace_ids))

    if ctype == "application/x-protobuf":
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceResponse,
        )

        return Response(
            content=ExportTraceServiceResponse().SerializeToString(),
            media_type="application/x-protobuf",
        )
    payload_out: dict[str, Any] = {"partialSuccess": {}}
    if accepted != len(spans):
        payload_out["partialSuccess"] = {
            "rejectedSpans": len(spans) - accepted,
            "errorMessage": "store rejected",
        }
    return Response(content=json.dumps(payload_out), media_type="application/json")
