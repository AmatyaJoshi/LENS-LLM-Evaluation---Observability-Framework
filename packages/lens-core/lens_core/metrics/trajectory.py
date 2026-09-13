"""Trajectory efficiency (SPEC.md §5.2, agent metric). No judge calls.

    step_ratio     = min(1, reference_steps / actual_steps)
    redundancy     = |tool calls repeating an earlier (name, args)| / |tool calls|
    loop_penalty   = 0.5 if a sequence of ≥2 tool names repeats back-to-back, else 0
    value          = step_ratio · (1 − redundancy) · (1 − loop_penalty)

``reference_steps`` comes from ``item.metadata["reference_steps"]``, else the
number of expected tools + 1, else the number of distinct tools called + 1
(the minimum plausible think-act sequence). Cost, latency and tokens are
reported in details for the dashboard but do not enter the value.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from lens_core.judges.base import Judge
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric

LOOP_PENALTY = 0.5


def detect_loop(names: list[str], min_len: int = 2) -> list[str] | None:
    """Return the repeated pattern if some window of length ≥ min_len occurs twice consecutively."""
    n = len(names)
    for length in range(min_len, n // 2 + 1):
        for start in range(0, n - 2 * length + 1):
            window = names[start : start + length]
            if window == names[start + length : start + 2 * length]:
                return window
    return None


@register_metric
class TrajectoryEfficiency(BaseMetric):
    name: ClassVar[str] = "trajectory_efficiency"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"trajectory"})
    description: ClassVar[str] = (
        "Steps vs a reference minimum, penalised for redundant tool calls and loops."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        assert item.trajectory is not None
        t = item.trajectory
        active_steps = [s for s in t.steps if s.llm_call or s.tool_calls or s.retrievals]
        actual = max(1, len(active_steps))
        tools = t.tool_calls
        distinct = {c.name for c in tools}

        ref_meta = item.metadata.get("reference_steps")
        if isinstance(ref_meta, int | float) and ref_meta > 0:
            reference = int(ref_meta)
            ref_source = "metadata.reference_steps"
        elif item.expected_tools:
            reference = len({e.name for e in item.expected_tools}) + 1
            ref_source = "expected_tools + 1"
        else:
            reference = len(distinct) + 1
            ref_source = "distinct tools + 1"
        step_ratio = min(1.0, reference / actual)

        seen: set[str] = set()
        redundant: list[str] = []
        for c in tools:
            key = f"{c.name}:{json.dumps(c.args, sort_keys=True, default=str)}"
            if key in seen:
                redundant.append(c.name)
            seen.add(key)
        redundancy = len(redundant) / len(tools) if tools else 0.0

        loop = detect_loop([c.name for c in tools])
        loop_penalty = LOOP_PENALTY if loop else 0.0

        value = step_ratio * (1 - redundancy) * (1 - loop_penalty)
        details: dict[str, Any] = {
            "actual_steps": actual,
            "reference_steps": reference,
            "reference_source": ref_source,
            "redundant_calls": redundant,
            "loop": loop,
            "tool_calls": len(tools),
            "distinct_tools": sorted(distinct),
            "total_tokens": t.total_tokens,
            "total_cost_usd": t.total_cost_usd,
            "duration_ms": t.duration_ms,
        }
        rationale = f"{actual} steps vs reference {reference}"
        if redundant:
            rationale += f"; {len(redundant)} redundant tool call(s)"
        if loop:
            rationale += f"; loop detected {loop}"
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=rationale,
            sub_scores={
                "step_ratio": step_ratio,
                "redundancy": redundancy,
                "loop_penalty": loop_penalty,
            },
            details=details,
        )
