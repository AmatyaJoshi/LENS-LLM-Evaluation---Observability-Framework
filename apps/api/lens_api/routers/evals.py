"""Evaluations API (SPEC.md §5.4, §8 page 3): runs, immutable scores, trends, compare,
online evaluation of a trace, metric catalogue."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from lens_api.db import get_session
from lens_api.deps import get_store, require_api_key
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import Dataset, EvalRun, Example, Score
from lens_api.services import evaluation as svc
from lens_api.settings import Settings, get_settings
from lens_core.metrics import MetricResult, MetricSpec, metric_specs

log = logging.getLogger("lens.evals")
router = APIRouter(tags=["evals"], dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------------------------


class RunIn(BaseModel):
    app: str
    dataset_id: UUID | None = None
    dataset_name: str | None = None
    git_sha: str | None = None
    mode: str = "offline"
    judge_tier: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)


class RunOut(BaseModel):
    id: UUID
    app: str
    dataset_id: UUID | None
    dataset_name: str | None = None
    git_sha: str | None
    mode: str
    judge_tier: str | None
    judge_model: str | None = None
    config_json: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, float] = Field(default_factory=dict)
    n_scores: int = 0
    n_items: int = 0
    cost_usd: float = 0.0
    errors: int = 0


class ScoreIn(BaseModel):
    result: MetricResult
    trace_id: str | None = None
    example_id: UUID | None = None
    judge_tier: str | None = None


class ScoresIn(BaseModel):
    scores: list[ScoreIn]


class ScoreOut(BaseModel):
    id: UUID
    run_id: UUID | None
    trace_id: str | None
    example_id: UUID | None
    metric: str
    metric_version: str
    value: float
    rationale: str | None
    sub_scores: dict[str, Any] | None
    details: dict[str, Any] | None
    judge_model: str | None
    judge_tier: str | None
    judge_prompt_version: str | None
    cost_usd: float | None
    latency_ms: float | None
    skipped: bool
    error: str | None
    created_at: datetime


class RunDetail(RunOut):
    items: list[dict[str, Any]] = Field(default_factory=list)
    distributions: dict[str, list[float]] = Field(default_factory=dict)


class CompareOut(BaseModel):
    a: RunOut
    b: RunOut
    deltas: dict[str, float]  # b - a per metric


class TrendPoint(BaseModel):
    run_id: UUID
    git_sha: str | None
    started_at: datetime
    mean: float
    n: int


class EvaluateIn(BaseModel):
    trace_id: str
    metrics: list[str] | None = None
    judge_tier: str = "frontier"


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------


def _run_out(session: Session, run: EvalRun) -> RunOut:
    scores = session.exec(select(Score).where(Score.run_id == run.id)).all()
    sums: dict[str, list[float]] = defaultdict(list)
    items: set[str] = set()
    cost = 0.0
    errors = 0
    judge_model = None
    for s in scores:
        items.add(s.trace_id or str(s.example_id))
        cost += s.cost_usd or 0.0
        judge_model = judge_model or s.judge_model
        if s.error:
            errors += 1
        elif not s.skipped:
            sums[s.metric].append(s.value)
    dataset_name = None
    if run.dataset_id:
        d = session.get(Dataset, run.dataset_id)
        dataset_name = d.name if d else None
    return RunOut(
        id=run.id,
        app=run.app,
        dataset_id=run.dataset_id,
        dataset_name=dataset_name,
        git_sha=run.git_sha,
        mode=run.mode,
        judge_tier=run.judge_tier,
        judge_model=judge_model or run.config_json.get("judge_model"),
        config_json=run.config_json,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics={k: sum(v) / len(v) for k, v in sums.items() if v},
        n_scores=len(scores),
        n_items=len(items),
        cost_usd=round(cost, 6),
        errors=errors,
    )


def _get_run(session: Session, run_id: UUID) -> EvalRun:
    run = session.get(EvalRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


# ---------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------


@router.get("/metrics", response_model=list[MetricSpec])
def list_metric_specs() -> list[MetricSpec]:
    return metric_specs()


@router.post("/evals/runs", response_model=RunOut, status_code=201)
def create_run(body: RunIn, session: Annotated[Session, Depends(get_session)]) -> RunOut:
    dataset_id = body.dataset_id
    if dataset_id is None and body.dataset_name:
        d = session.exec(select(Dataset).where(Dataset.name == body.dataset_name)).first()
        if not d:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"dataset {body.dataset_name!r} not found"
            )
        dataset_id = d.id
    run = EvalRun(
        app=body.app,
        dataset_id=dataset_id,
        git_sha=body.git_sha,
        mode=body.mode,
        judge_tier=body.judge_tier,
        config_json=body.config_json,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return _run_out(session, run)


@router.get("/evals/runs", response_model=list[RunOut])
def list_runs(
    session: Annotated[Session, Depends(get_session)],
    app: str | None = None,
    dataset_id: UUID | None = None,
    mode: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RunOut]:
    q = select(EvalRun)
    if app:
        q = q.where(EvalRun.app == app)
    if dataset_id:
        q = q.where(EvalRun.dataset_id == dataset_id)
    if mode:
        q = q.where(EvalRun.mode == mode)
    runs = session.exec(q.order_by(EvalRun.started_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [_run_out(session, r) for r in runs]


@router.get("/evals/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: UUID, session: Annotated[Session, Depends(get_session)]) -> RunDetail:
    run = _get_run(session, run_id)
    base = _run_out(session, run)
    scores = session.exec(
        select(Score).where(Score.run_id == run_id).order_by(Score.created_at)
    ).all()  # type: ignore[arg-type]
    by_item: dict[str, dict[str, Any]] = {}
    dists: dict[str, list[float]] = defaultdict(list)
    example_cache: dict[UUID, Example | None] = {}
    for s in scores:
        key = s.trace_id or str(s.example_id)
        entry = by_item.setdefault(
            key,
            {
                "trace_id": s.trace_id,
                "example_id": str(s.example_id) if s.example_id else None,
                "scores": {},
            },
        )
        if s.example_id and "input" not in entry:
            if s.example_id not in example_cache:
                example_cache[s.example_id] = session.get(Example, s.example_id)
            ex = example_cache[s.example_id]
            if ex:
                entry["input"] = ex.input[:300]
                entry["expected_output"] = (ex.expected_output or "")[:300]
                entry["output"] = (ex.output or "")[:300]
        entry["scores"][s.metric] = {
            "value": s.value,
            "rationale": s.rationale,
            "skipped": s.skipped,
            "error": s.error,
            "sub_scores": s.sub_scores,
            "judge_model": s.judge_model,
            "judge_prompt_version": s.judge_prompt_version,
            "cost_usd": s.cost_usd,
            "latency_ms": s.latency_ms,
        }
        if not s.skipped and not s.error:
            dists[s.metric].append(s.value)
    return RunDetail(**base.model_dump(), items=list(by_item.values()), distributions=dict(dists))


@router.post("/evals/runs/{run_id}/scores")
def add_scores(
    run_id: UUID, body: ScoresIn, session: Annotated[Session, Depends(get_session)]
) -> dict[str, int]:
    _get_run(session, run_id)
    for s in body.scores:
        session.add(
            svc.score_row(
                run_id,
                s.result,
                trace_id=s.trace_id,
                example_id=s.example_id,
                judge_tier=s.judge_tier,
            )
        )
    session.commit()
    return {"inserted": len(body.scores)}


@router.post("/evals/runs/{run_id}/finish", response_model=RunOut)
def finish_run(run_id: UUID, session: Annotated[Session, Depends(get_session)]) -> RunOut:
    run = _get_run(session, run_id)
    run.finished_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    session.refresh(run)
    return _run_out(session, run)


@router.get("/evals/compare", response_model=CompareOut)
def compare_runs(a: UUID, b: UUID, session: Annotated[Session, Depends(get_session)]) -> CompareOut:
    ra, rb = _run_out(session, _get_run(session, a)), _run_out(session, _get_run(session, b))
    deltas = {m: rb.metrics[m] - ra.metrics[m] for m in ra.metrics if m in rb.metrics}
    return CompareOut(a=ra, b=rb, deltas=deltas)


@router.get("/evals/trends", response_model=list[TrendPoint])
def trends(
    metric: str,
    session: Annotated[Session, Depends(get_session)],
    app: str | None = None,
    dataset_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TrendPoint]:
    q = select(EvalRun).where(EvalRun.finished_at.is_not(None))
    if app:
        q = q.where(EvalRun.app == app)
    if dataset_id:
        q = q.where(EvalRun.dataset_id == dataset_id)
    runs = session.exec(q.order_by(EvalRun.started_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    points: list[TrendPoint] = []
    for r in runs:
        vals = [
            s.value
            for s in session.exec(
                select(Score).where(Score.run_id == r.id, Score.metric == metric)
            ).all()
            if not s.skipped and not s.error
        ]
        if vals:
            points.append(
                TrendPoint(
                    run_id=r.id,
                    git_sha=r.git_sha,
                    started_at=r.started_at,
                    mean=sum(vals) / len(vals),
                    n=len(vals),
                )
            )
    return list(reversed(points))


@router.get("/evals/traces/{trace_id}/scores", response_model=list[ScoreOut])
def trace_scores(
    trace_id: str, session: Annotated[Session, Depends(get_session)]
) -> list[ScoreOut]:
    rows = session.exec(
        select(Score).where(Score.trace_id == trace_id).order_by(Score.created_at.desc())
    ).all()  # type: ignore[attr-defined]
    return [ScoreOut.model_validate(r.model_dump()) for r in rows]


@router.post("/evals/evaluate", status_code=202)
async def evaluate_now(
    body: EvaluateIn,
    request: Request,
    store: Annotated[SpanStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Score one ingested trace now (online mode). Runs in-process in the background,
    or on the Celery worker when ``LENS_EVAL_DISPATCH=celery``."""
    if not await store.get_trace(body.trace_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
    metrics = body.metrics or [m.strip() for m in settings.eval_metrics.split(",") if m.strip()]
    if settings.eval_dispatch == "celery":
        from celery import Celery

        Celery(broker=settings.redis_url).send_task(
            "lens.evaluate_trace", args=[body.trace_id, metrics, body.judge_tier], queue="lens.eval"
        )
        return {
            "status": "queued",
            "dispatch": "celery",
            "trace_id": body.trace_id,
            "metrics": metrics,
        }

    # Inline mode: run to completion and return the scores, so the caller (e.g. the
    # dashboard's "Score now" button) sees results immediately. This is reliable, unlike
    # fire-and-forget background tasks; use dispatch="celery" for high-volume async work.
    engine = request.app.state.db_engine
    try:
        run, summary = await svc.evaluate_trace(
            body.trace_id,
            store=store,
            engine=engine,
            judge=svc.judge_for(body.judge_tier),
            metrics=metrics,
            judge_tier=body.judge_tier,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("online evaluation failed for %s", body.trace_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"evaluation failed: {exc}") from exc
    return {
        "status": "done",
        "dispatch": "inline",
        "trace_id": body.trace_id,
        "run_id": str(run.id),
        "metrics": summary.metrics,
        "cost_usd": summary.cost_usd,
    }
