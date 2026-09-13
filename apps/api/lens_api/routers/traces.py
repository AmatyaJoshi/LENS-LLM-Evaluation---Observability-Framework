"""Trace read API: list, span detail, reconstructed trajectory."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from lens_api.deps import get_store, require_api_key
from lens_api.ingest import normalize
from lens_api.models.clickhouse import SpanStore
from lens_core.trace import Span, Trajectory, build_trajectory

router = APIRouter(prefix="/traces", tags=["traces"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_traces(
    store: Annotated[SpanStore, Depends(get_store)],
    app: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, Any]]:
    return [dict(t) for t in await store.list_traces(app=app, limit=limit)]


@router.get("/{trace_id}")
async def get_trace(trace_id: str, store: Annotated[SpanStore, Depends(get_store)]) -> list[Span]:
    spans = await store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    return spans


@router.get("/{trace_id}/trajectory")
async def get_trajectory(
    trace_id: str, store: Annotated[SpanStore, Depends(get_store)]
) -> Trajectory:
    spans = await store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    return build_trajectory(spans, normalize.derive(spans))
