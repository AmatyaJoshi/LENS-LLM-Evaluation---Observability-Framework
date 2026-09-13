"""Red team API (SPEC.md §6, §8 page 5): probe catalogue, runs, per-probe results with
lineage, ASR over time (the before/after-defence chart), and live-flagged traffic."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from lens_api.db import get_session
from lens_api.deps import get_store, require_api_key
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import ProbeResult, RedteamRun
from lens_api.services import redteam as svc
from lens_core.redteam import ALL_MUTATORS, load_probes, probe_stats
from lens_core.redteam.probes import Category

router = APIRouter(prefix="/redteam", tags=["redteam"], dependencies=[Depends(require_api_key)])

PROBES_DIR = Path("data/probes")


class ProbeCatalogue(BaseModel):
    total: int
    by_category: dict[str, int]
    categories: list[str]
    mutators: list[str]


class RunOut(BaseModel):
    id: UUID
    app: str
    target: str
    git_sha: str | None
    defence: str | None
    total_probes: int
    successes: int
    asr: float
    detector_caught: int
    detector_caught_rate: float
    started_at: datetime
    finished_at: datetime | None


class ImportIn(BaseModel):
    app: str
    target: str
    git_sha: str | None = None
    defence: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any]


class LaunchIn(BaseModel):
    app: str
    target: str
    categories: list[Category] | None = None
    mutators: list[str] = Field(default_factory=list)
    judge_tier: str | None = None
    git_sha: str | None = None
    defence: str | None = None


class ProbeResultOut(BaseModel):
    id: UUID
    probe_id: str
    parent_probe_id: str | None
    category: str
    tactic: str | None
    mutator: str | None
    response: str | None
    success: bool
    success_reason: str | None
    detector_score: float | None
    detector_flagged: bool
    trace_id: str | None


def _run_out(run: RedteamRun) -> RunOut:
    return RunOut(
        id=run.id,
        app=run.app,
        target=run.target,
        git_sha=run.git_sha,
        defence=run.defence,
        total_probes=run.total_probes,
        successes=run.successes,
        asr=run.asr,
        detector_caught=run.detector_caught,
        detector_caught_rate=run.detector_caught / run.successes if run.successes else 0.0,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/probes", response_model=ProbeCatalogue)
def probes() -> ProbeCatalogue:
    library = load_probes(PROBES_DIR) if PROBES_DIR.exists() else []
    stats = probe_stats(library)
    total = stats.pop("total", 0)
    return ProbeCatalogue(
        total=total,
        by_category=stats,
        categories=sorted(stats),
        mutators=list(ALL_MUTATORS),
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    session: Annotated[Session, Depends(get_session)],
    app: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RunOut]:
    q = select(RedteamRun)
    if app:
        q = q.where(RedteamRun.app == app)
    runs = session.exec(q.order_by(RedteamRun.started_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [_run_out(r) for r in runs]


@router.post("/runs/import", response_model=RunOut, status_code=201)
def import_run(body: ImportIn, request: Request) -> RunOut:
    """Store a report produced by ``lens redteam`` (which does the attacking)."""
    run = svc.import_report(request.app.state.db_engine, body.model_dump())
    return _run_out(run)


@router.post("/runs/launch", response_model=RunOut, status_code=202)
def launch_run(
    body: LaunchIn, request: Request, session: Annotated[Session, Depends(get_session)]
) -> RunOut:
    """Queue a red-team run on the Celery worker (the worker does the attacking)."""
    settings = request.app.state.settings
    run = RedteamRun(
        app=body.app,
        target=body.target,
        git_sha=body.git_sha,
        defence=body.defence,
        config_json={
            "categories": body.categories,
            "mutators": body.mutators,
            "judge_tier": body.judge_tier,
            "probes": str(PROBES_DIR),
        },
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    try:
        from celery import Celery

        Celery(broker=settings.redis_url).send_task(
            "lens.run_redteam", args=[str(run.id)], queue="lens.redteam"
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"could not queue run: {exc}"
        ) from exc
    return _run_out(run)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, session: Annotated[Session, Depends(get_session)]) -> RunOut:
    run = session.get(RedteamRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return _run_out(run)


@router.get("/runs/{run_id}/results", response_model=list[ProbeResultOut])
def run_results(
    run_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    category: str | None = None,
    success: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[ProbeResultOut]:
    if not session.get(RedteamRun, run_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    q = select(ProbeResult).where(ProbeResult.run_id == run_id)
    if category:
        q = q.where(ProbeResult.category == category)
    if success is not None:
        q = q.where(ProbeResult.success == success)
    rows = session.exec(q.order_by(ProbeResult.success.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [ProbeResultOut.model_validate(r.model_dump()) for r in rows]


@router.get("/asr")
def asr_over_time(
    session: Annotated[Session, Depends(get_session)], app: str, category: str | None = None
) -> list[dict[str, Any]]:
    """ASR per run over time; the before/after-defence chart (SPEC.md §6.4)."""
    return svc.asr_over_time(session, app, category)


@router.get("/flagged")
async def flagged_traffic(
    store: Annotated[SpanStore, Depends(get_store)],
    app: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    """Live traffic the injection detector flagged during ingest (SPEC.md §6.5)."""
    page = await store.list_traces(_flag_filter(app, limit))
    out: list[dict[str, Any]] = []
    for summary in page.items:
        spans = await store.get_trace(summary.trace_id)
        flagged = [
            {
                "span_id": s.span_id,
                "kind": s.kind,
                "score": s.attributes.get("lens.security.injection_score"),
                "reasons": s.attributes.get("lens.security.reasons"),
            }
            for s in spans
            if s.attributes.get("lens.security.flagged")
        ]
        if flagged:
            out.append(
                {
                    "trace_id": summary.trace_id,
                    "app": summary.app,
                    "start_ns": summary.start_ns,
                    "flagged_spans": flagged,
                    "max_score": max((f["score"] or 0.0) for f in flagged),
                }
            )
    return out[:limit]


def _flag_filter(app: str | None, limit: int) -> Any:
    from lens_api.models.clickhouse import TraceFilter

    return TraceFilter(app=app, limit=max(limit * 4, 100))
