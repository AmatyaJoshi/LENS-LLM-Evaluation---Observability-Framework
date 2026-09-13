"""Metric interface (SPEC.md §5.1).

A metric is pure: it receives an ``EvalItem`` and a ``Judge`` and returns a
``MetricResult`` with a value in [0, 1], a rationale, sub-scores and full
provenance (judge model, prompt version, cost, latency). Metrics never call a
live LLM in tests; they are exercised with a ``CassetteJudge``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from lens_core.judges.base import Judge
from lens_core.trace.model import Trajectory

Requirement = Literal[
    "input", "output", "contexts", "expected_output", "trajectory", "expected_tools"
]


class ExpectedTool(BaseModel):
    """Reference tool spec for tool-call correctness."""

    name: str
    args: dict[str, Any] | None = None  # expected argument values (subset match)
    arg_types: dict[str, str] | None = None  # expected JSON types per key
    required: bool = True


class EvalItem(BaseModel):
    id: str | None = None
    input: str | None = None
    output: str | None = None
    contexts: list[str] = Field(default_factory=list)
    expected_output: str | None = None
    trajectory: Trajectory | None = None
    expected_tools: list[ExpectedTool] | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_trajectory(cls, t: Trajectory, **overrides: Any) -> EvalItem:
        contexts = [d.text for r in t.retrievals for d in r.documents if d.text]
        expected = t.metadata.get("lens.eval.expected_output")
        return cls(
            id=t.trace_id,
            trace_id=t.trace_id,
            input=t.user_input,
            output=t.final_output,
            contexts=contexts,
            expected_output=str(expected) if expected is not None else None,
            trajectory=t,
            metadata=dict(t.metadata),
            **overrides,
        )


class MetricResult(BaseModel):
    metric: str
    version: str
    value: float
    rationale: str = ""
    sub_scores: dict[str, float] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    judge_model: str | None = None
    judge_prompt_version: str | None = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    skipped: bool = False


@runtime_checkable
class Metric(Protocol):
    name: str
    version: str
    requires: frozenset[Requirement]

    async def score(self, item: EvalItem, judge: Judge) -> MetricResult: ...


class BaseMetric(ABC):
    """Handles requirement checks, timing, cost accounting and error capture."""

    name: ClassVar[str]
    version: ClassVar[str]
    requires: ClassVar[frozenset[Requirement]]
    higher_is_better: ClassVar[bool] = True
    description: ClassVar[str] = ""

    def missing(self, item: EvalItem) -> list[str]:
        missing: list[str] = []
        for req in sorted(self.requires):
            value = getattr(item, req, None)
            if value is None or (isinstance(value, list) and len(value) == 0):
                missing.append(req)
        return missing

    async def score(self, item: EvalItem, judge: Judge) -> MetricResult:
        missing = self.missing(item)
        if missing:
            return MetricResult(
                metric=self.name,
                version=self.version,
                value=0.0,
                rationale=f"skipped: item lacks {', '.join(missing)}",
                skipped=True,
            )
        t0 = time.perf_counter()
        cost_before = judge.cost_usd
        try:
            result = await self._score(item, judge)
        except Exception as exc:  # noqa: BLE001 - metrics must never crash a run
            result = MetricResult(
                metric=self.name,
                version=self.version,
                value=0.0,
                rationale=f"error: {type(exc).__name__}: {exc}",
                error=f"{type(exc).__name__}: {exc}",
            )
        result.metric = self.name
        result.version = self.version
        result.value = max(0.0, min(1.0, float(result.value)))
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.cost_usd = round(judge.cost_usd - cost_before, 8)
        result.judge_model = result.judge_model or judge.model
        return result

    @abstractmethod
    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult: ...
