"""Trace read API: list/search, span detail, reconstructed trajectory, apps, overview stats."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from lens_api.deps import get_store, require_api_key
from lens_api.ingest import normalize
from lens_api.models.clickhouse import (
    AppUsage,
    OverviewStats,
    SpanStore,
    TraceFilter,
    TracePage,
)
from lens_core.trace import Span, Trajectory, build_trajectory

router = APIRouter(tags=["traces"], dependencies=[Depends(require_api_key)])

_WINDOWS_NS: dict[str, int] = {
    "15m": 15 * 60 * 10**9,
    "1h": 60 * 60 * 10**9,
    "6h": 6 * 60 * 60 * 10**9,
    "24h": 24 * 60 * 60 * 10**9,
    "7d": 7 * 24 * 60 * 60 * 10**9,
    "30d": 30 * 24 * 60 * 60 * 10**9,
    "all": 0,
}


@router.get("/traces", response_model=TracePage)
async def list_traces(
    store: Annotated[SpanStore, Depends(get_store)],
    app: str | None = None,
    status_: Annotated[str | None, Query(alias="status", pattern="^(ok|error)$")] = None,
    model: str | None = None,
    provider: str | None = None,
    kind: Annotated[str | None, Query(pattern="^(llm|tool|retrieval)$")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    since_ns: int | None = None,
    until_ns: int | None = None,
    min_duration_ms: float | None = None,
    max_duration_ms: float | None = None,
    has_tools: bool | None = None,
    has_retrievals: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[
        str, Query(pattern="^(start_desc|start_asc|duration_desc|tokens_desc)$")
    ] = "start_desc",
) -> TracePage:
    flt = TraceFilter(
        app=app,
        status=status_,
        model=model,
        provider=provider,
        kind=kind,
        q=q,
        since_ns=since_ns,
        until_ns=until_ns,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        has_tools=has_tools,
        has_retrievals=has_retrievals,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return await store.list_traces(flt)


@router.get("/traces/{trace_id}", response_model=list[Span])
async def get_trace(trace_id: str, store: Annotated[SpanStore, Depends(get_store)]) -> list[Span]:
    spans = await store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    return spans


@router.get("/traces/{trace_id}/trajectory", response_model=Trajectory)
async def get_trajectory(
    trace_id: str, store: Annotated[SpanStore, Depends(get_store)]
) -> Trajectory:
    spans = await store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    return build_trajectory(spans, normalize.derive(spans))


def _tokens(text: str | None) -> set[str]:
    return {w for w in (text or "").lower().split() if len(w) > 2}


@router.get("/traces/{trace_id}/similar")
async def similar_traces(
    trace_id: str,
    store: Annotated[SpanStore, Depends(get_store)],
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
) -> list[dict[str, object]]:
    """Find traces most similar to this one (SPEC.md §8 'similar failures').

    Ranks other traces by Jaccard token overlap of their input+output previews.
    Works on any span store; when embeddings/pgvector are available they can replace
    this lexical fallback without changing the API.
    """
    spans = await store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    target = build_trajectory(spans, normalize.derive(spans))
    anchor = _tokens(target.user_input) | _tokens(target.final_output)
    if not anchor:
        return []
    page = await store.list_traces(TraceFilter(app=target.app, limit=500))
    scored: list[dict[str, object]] = []
    for t in page.items:
        if t.trace_id == trace_id:
            continue
        other = _tokens(t.input_preview) | _tokens(t.output_preview)
        if not other:
            continue
        inter = len(anchor & other)
        if inter == 0:
            continue
        score = inter / len(anchor | other)
        scored.append(
            {
                "trace_id": t.trace_id,
                "app": t.app,
                "root_name": t.root_name,
                "status": t.status,
                "input_preview": t.input_preview,
                "duration_ms": t.duration_ms,
                "similarity": round(score, 3),
            }
        )
    scored.sort(key=lambda x: x["similarity"], reverse=True)  # type: ignore[arg-type,return-value]
    return scored[:limit]


@router.get("/apps", response_model=list[AppUsage])
async def list_apps(store: Annotated[SpanStore, Depends(get_store)]) -> list[AppUsage]:
    return await store.list_apps()


@router.get("/stats/overview", response_model=OverviewStats)
async def overview(
    store: Annotated[SpanStore, Depends(get_store)],
    app: str | None = None,
    window: Annotated[str, Query(pattern="^(15m|1h|6h|24h|7d|30d|all)$")] = "24h",
    buckets: Annotated[int, Query(ge=4, le=200)] = 48,
) -> OverviewStats:
    now_ns = time.time_ns()
    span_ns = _WINDOWS_NS[window]
    since_ns = now_ns - span_ns if span_ns else 0
    bucket_ns = max((now_ns - since_ns) // buckets, 60 * 10**9)
    return await store.overview(app=app, since_ns=since_ns, until_ns=now_ns, bucket_ns=bucket_ns)
