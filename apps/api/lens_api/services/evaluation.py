"""Evaluation service: turn traces / dataset examples into EvalItems, run the
engine, and persist EvalRun + immutable Score rows (SPEC.md §3.2, §5.4)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session, select

from lens_api.ingest import normalize
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import EvalRun, Example, Score
from lens_core.datasets.schema import ExampleRecord
from lens_core.judges.base import Judge
from lens_core.judges.router import JudgeRouter
from lens_core.metrics import Engine as MetricEngine
from lens_core.metrics import EvalItem, ItemResults, MetricResult, RunSummary
from lens_core.trace.model import Trajectory

log = logging.getLogger("lens.eval")

DEFAULT_ONLINE_METRICS = ("faithfulness", "answer_relevance", "hallucination", "safety")


def example_to_record(e: Example) -> ExampleRecord:
    return ExampleRecord(
        id=e.external_id or str(e.id),
        input=e.input,
        output=e.output,
        expected_output=e.expected_output,
        contexts=list(e.contexts or []),
        expected_tools=e.expected_tools,  # type: ignore[arg-type]
        metadata=dict(e.metadata_ or {}),
        split=e.split,  # type: ignore[arg-type]
        source_trace_id=e.source_trace_id,
    )


def score_row(
    run_id: UUID | None,
    result: MetricResult,
    *,
    trace_id: str | None,
    example_id: UUID | None,
    judge_tier: str | None,
) -> Score:
    return Score(
        run_id=run_id,
        trace_id=trace_id,
        example_id=example_id,
        metric=result.metric,
        metric_version=result.version,
        value=result.value,
        rationale=result.rationale,
        sub_scores=result.sub_scores or None,
        details=result.details or None,
        judge_model=result.judge_model,
        judge_tier=judge_tier,
        judge_prompt_version=result.judge_prompt_version,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        skipped=result.skipped,
        error=result.error,
    )


def persist_results(
    session: Session,
    run: EvalRun,
    results: Sequence[ItemResults],
    *,
    example_ids: dict[str, UUID] | None = None,
    judge_tier: str | None,
) -> int:
    n = 0
    for ir in results:
        example_id = (example_ids or {}).get(ir.item_id or "") if example_ids else None
        for r in ir.results:
            session.add(
                score_row(
                    run.id, r, trace_id=ir.trace_id, example_id=example_id, judge_tier=judge_tier
                )
            )
            n += 1
    session.commit()
    return n


async def evaluate_trace(
    trace_id: str,
    *,
    store: SpanStore,
    engine: Engine,
    judge: Judge,
    metrics: Sequence[str] = DEFAULT_ONLINE_METRICS,
    judge_tier: str = "frontier",
    mode: str = "online",
) -> tuple[EvalRun, RunSummary]:
    spans = await store.get_trace(trace_id)
    if not spans:
        raise LookupError(f"trace {trace_id} not found")
    trajectory: Trajectory = _build(spans)
    item = EvalItem.from_trajectory(trajectory)
    metric_engine = MetricEngine(judge, metrics=list(metrics), concurrency=4)
    results = await metric_engine.run([item])
    summary = metric_engine.summarise(results)
    with Session(engine) as session:
        run = EvalRun(
            app=trajectory.app,
            mode=mode,
            judge_tier=judge_tier,
            config_json={
                "metrics": list(metrics),
                "judge_model": judge.model,
                "trace_id": trace_id,
            },
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        persist_results(session, run, results, judge_tier=judge_tier)
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        session.refresh(run)
    return run, summary


def _build(spans: Any) -> Trajectory:
    from lens_core.trace import build_trajectory

    return build_trajectory(spans, normalize.derive(spans))


def judge_for(tier: str) -> Judge:
    return JudgeRouter.from_env().get(tier)


def run_means(session: Session, run_id: UUID) -> dict[str, float]:
    rows = session.exec(
        select(Score).where(Score.run_id == run_id, Score.skipped.is_(False), Score.error.is_(None))
    ).all()
    sums: dict[str, list[float]] = {}
    for s in rows:
        sums.setdefault(s.metric, []).append(s.value)
    return {k: sum(v) / len(v) for k, v in sums.items() if v}
