"""OTLP/HTTP ingest endpoint: ``POST /v1/traces`` (JSON or protobuf, optionally gzip).

gRPC ingest is provided by the OpenTelemetry Collector (apps/collector), which
receives OTLP/gRPC + OTLP/HTTP on 4317/4318 and forwards to this endpoint.
"""

from __future__ import annotations

import gzip
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from lens_api.deps import get_store, require_api_key
from lens_api.ingest import normalize
from lens_api.ingest.redact import build_redactor, redact_span
from lens_api.models.clickhouse import SpanStore
from lens_api.settings import Settings, get_settings
from lens_api.ws import hub

router = APIRouter(tags=["ingest"])

_redactor = build_redactor()


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
            }
        )

    payload_out = (
        {"partialSuccess": {}}
        if accepted == len(spans)
        else {
            "partialSuccess": {
                "rejectedSpans": len(spans) - accepted,
                "errorMessage": "store rejected",
            }
        }
    )
    if ctype == "application/x-protobuf":
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceResponse,
        )

        return Response(
            content=ExportTraceServiceResponse().SerializeToString(),
            media_type="application/x-protobuf",
        )
    return Response(content=json.dumps(payload_out), media_type="application/json")
