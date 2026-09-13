"""Celery tasks (SPEC.md §2.2): evaluate_trace, run_dataset_eval, run_redteam.

Tasks reuse the API's services and settings so the worker and the API produce
identical Score / ProbeResult rows.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from lens_api.db import engine_for
from lens_api.models.clickhouse import make_store
from lens_api.services import evaluation as svc
from lens_api.settings import get_settings
from lens_worker.celery_app import app

log = logging.getLogger("lens.worker")


@app.task(name="lens.ping")
def ping() -> str:
    return "pong"


@app.task(name="lens.evaluate_trace", bind=True, max_retries=2, default_retry_delay=30)
def evaluate_trace(
    self: Any, trace_id: str, metrics: list[str] | None = None, judge_tier: str = "frontier"
) -> dict[str, Any]:
    """Online evaluation of one ingested trace (SPEC.md §5.4)."""
    settings = get_settings()
    store = make_store(settings)
    engine = engine_for(settings.postgres_dsn)
    chosen = metrics or [m.strip() for m in settings.eval_metrics.split(",") if m.strip()]
    try:
        run, summary = asyncio.run(
            svc.evaluate_trace(
                trace_id,
                store=store,
                engine=engine,
                judge=svc.judge_for(judge_tier),
                metrics=chosen,
                judge_tier=judge_tier,
            )
        )
    except LookupError as exc:
        # span batches can arrive slightly after the first one; retry briefly
        raise self.retry(exc=exc) from exc
    return {
        "trace_id": trace_id,
        "run_id": str(run.id),
        "metrics": summary.metrics,
        "cost_usd": summary.cost_usd,
    }


@app.task(name="lens.run_dataset_eval", bind=True)
def run_dataset_eval(
    self: Any, run_id: str, metrics: list[str], judge_tier: str = "frontier"
) -> dict[str, Any]:
    """Score every example of the run's dataset that has a recorded output (SPEC.md §5.4 offline)."""
    from datetime import UTC, datetime

    from sqlmodel import Session, select

    from lens_api.models.sql import EvalRun, Example
    from lens_core.metrics import Engine as MetricEngine

    settings = get_settings()
    engine = engine_for(settings.postgres_dsn)
    judge = svc.judge_for(judge_tier)
    with Session(engine) as session:
        run = session.get(EvalRun, UUID(run_id))
        if run is None or run.dataset_id is None:
            return {"run_id": run_id, "status": "missing run or dataset"}
        examples = session.exec(select(Example).where(Example.dataset_id == run.dataset_id)).all()
        records = [svc.example_to_record(e) for e in examples if e.output]
        example_ids = {svc.example_to_record(e).id or "": e.id for e in examples}
        items = [r.to_eval_item() for r in records]
        metric_engine = MetricEngine(judge, metrics=metrics, concurrency=4)
        results = asyncio.run(metric_engine.run(items))
        n = svc.persist_results(
            session, run, results, example_ids=example_ids, judge_tier=judge_tier
        )
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        summary = metric_engine.summarise(results)
    return {"run_id": run_id, "scores": n, "metrics": summary.metrics, "cost_usd": summary.cost_usd}


@app.task(name="lens.run_redteam", bind=True)
def run_redteam(self: Any, run_id: str) -> dict[str, Any]:
    """Red-team run against a target (SPEC.md §6); body lands with the red-team service."""
    from lens_api.services import redteam as rt

    return asyncio.run(rt.execute_run(UUID(run_id)))
