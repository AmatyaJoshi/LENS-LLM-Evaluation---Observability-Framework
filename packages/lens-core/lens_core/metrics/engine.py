"""Evaluation engine: runs metrics over items concurrently with content-hash caching.

Caching key = sha1(metric@version, judge model, item content). The cache is an
in-memory dict by default; pass a directory to persist across CLI runs (the
"cache by content hash" mitigation in SPEC.md §13).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from lens_core.judges.base import Judge
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult
from lens_core.metrics.registry import get_metric


class ItemResults(BaseModel):
    item_id: str | None
    trace_id: str | None
    results: list[MetricResult]


class RunSummary(BaseModel):
    n_items: int
    metrics: dict[str, float]  # mean value per metric over scored (non-skipped) items
    skipped: dict[str, int] = Field(default_factory=dict)
    errors: dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0
    judge_calls: int = 0
    p95_judge_latency_ms: float = 0.0


def _content_key(metric: BaseMetric, judge: Judge, item: EvalItem) -> str:
    payload = {
        "metric": f"{metric.name}@{metric.version}",
        "judge": judge.model,
        "input": item.input,
        "output": item.output,
        "contexts": item.contexts,
        "expected_output": item.expected_output,
        "expected_tools": [t.model_dump() for t in item.expected_tools or []],
        "trajectory": item.trajectory.model_dump(mode="json") if item.trajectory else None,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class ResultCache:
    def __init__(self, directory: Path | None = None) -> None:
        self._mem: dict[str, MetricResult] = {}
        self._dir = directory
        if directory:
            directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> MetricResult | None:
        if key in self._mem:
            return self._mem[key]
        if self._dir:
            p = self._dir / f"{key}.json"
            if p.exists():
                r = MetricResult.model_validate_json(p.read_text(encoding="utf-8"))
                self._mem[key] = r
                return r
        return None

    def put(self, key: str, result: MetricResult) -> None:
        self._mem[key] = result
        if self._dir:
            (self._dir / f"{key}.json").write_text(result.model_dump_json(), encoding="utf-8")


class Engine:
    def __init__(
        self,
        judge: Judge,
        *,
        metrics: Sequence[BaseMetric | str],
        concurrency: int = 4,
        cache: ResultCache | None = None,
        on_result: Callable[[EvalItem, MetricResult], None] | None = None,
    ) -> None:
        self.judge = judge
        self.metrics: list[BaseMetric] = [
            get_metric(m) if isinstance(m, str) else m for m in metrics
        ]
        self._sem = asyncio.Semaphore(concurrency)
        self.cache = cache or ResultCache()
        self.on_result = on_result

    async def score_item(self, item: EvalItem) -> ItemResults:
        results: list[MetricResult] = []
        for metric in self.metrics:
            key = _content_key(metric, self.judge, item)
            cached = self.cache.get(key)
            if cached is not None:
                result = cached.model_copy(update={"details": {**cached.details, "cached": True}})
            else:
                async with self._sem:
                    result = await metric.score(item, self.judge)
                if not result.error:
                    self.cache.put(key, result)
            results.append(result)
            if self.on_result:
                self.on_result(item, result)
        return ItemResults(item_id=item.id, trace_id=item.trace_id, results=results)

    async def run(self, items: Iterable[EvalItem]) -> list[ItemResults]:
        return list(await asyncio.gather(*(self.score_item(i) for i in items)))

    def summarise(self, results: Sequence[ItemResults]) -> RunSummary:
        sums: dict[str, list[float]] = {}
        skipped: dict[str, int] = {}
        errors: dict[str, int] = {}
        for ir in results:
            for r in ir.results:
                if r.skipped:
                    skipped[r.metric] = skipped.get(r.metric, 0) + 1
                elif r.error:
                    errors[r.metric] = errors.get(r.metric, 0) + 1
                else:
                    sums.setdefault(r.metric, []).append(r.value)
        return RunSummary(
            n_items=len(results),
            metrics={k: sum(v) / len(v) for k, v in sums.items() if v},
            skipped=skipped,
            errors=errors,
            cost_usd=round(self.judge.stats.cost_usd, 6),
            judge_calls=self.judge.stats.calls,
            p95_judge_latency_ms=self.judge.stats.p95_latency_ms,
        )
