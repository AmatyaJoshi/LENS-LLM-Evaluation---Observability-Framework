"""Tool-call correctness (SPEC.md §5.2, agent metric).

Four sub-scores, averaged over those that apply:

    right_tool     F1 between the set of expected tool names and the set of tools actually called
    args_valid     fraction of expected argument constraints satisfied
                   (``arg_types`` JSON-type checks and ``args`` expected-value subset matches)
    args_semantic  judge grade (``tool_args_semantic``, 1-5 → [0,1]) of each matched call
    result_used    judge yes/no (``result_used``): final answer reflects the last tool result?

Requires a trajectory and an ``expected_tools`` spec (from the dataset example).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import RubricScore, YesNo, rubric_to_unit
from lens_core.metrics.base import BaseMetric, EvalItem, ExpectedTool, MetricResult, Requirement
from lens_core.metrics.registry import register_metric
from lens_core.trace.model import ToolCall

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def _f1(expected: set[str], actual: set[str]) -> float:
    if not expected and not actual:
        return 1.0
    tp = len(expected & actual)
    if tp == 0:
        return 0.0
    precision = tp / len(actual)
    recall = tp / len(expected)
    return 2 * precision * recall / (precision + recall)


def _args_valid(spec: ExpectedTool, call: ToolCall) -> tuple[int, int]:
    """(satisfied, total) constraints for one expected tool against an actual call."""
    satisfied = total = 0
    for key, jtype in (spec.arg_types or {}).items():
        total += 1
        value = call.args.get(key)
        types = _JSON_TYPES.get(jtype, ())
        if (
            value is not None
            and (not types or isinstance(value, types))
            and not (jtype != "boolean" and isinstance(value, bool))
        ):
            satisfied += 1
    for key, expected in (spec.args or {}).items():
        total += 1
        if call.args.get(key) == expected:
            satisfied += 1
    return satisfied, total


@register_metric
class ToolCorrectness(BaseMetric):
    name: ClassVar[str] = "tool_correctness"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"trajectory", "expected_tools"})
    description: ClassVar[str] = (
        "Right tool chosen, arguments valid and semantically right, result used in the answer."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        assert item.trajectory is not None and item.expected_tools is not None
        calls = item.trajectory.tool_calls
        expected_names = {t.name for t in item.expected_tools if t.required}
        actual_names = {c.name for c in calls}
        sub: dict[str, float] = {"right_tool": _f1(expected_names, actual_names)}
        details: dict[str, Any] = {
            "expected": sorted(expected_names),
            "actual": [c.name for c in calls],
            "missing": sorted(expected_names - actual_names),
            "unexpected": sorted(actual_names - {t.name for t in item.expected_tools}),
        }
        versions: list[str] = []

        # argument constraints
        sat = tot = 0
        for spec in item.expected_tools:
            for call in (c for c in calls if c.name == spec.name):
                s, t = _args_valid(spec, call)
                sat += s
                tot += t
        if tot:
            sub["args_valid"] = sat / tot

        # semantic argument check by judge, one call per matched tool
        matched = [c for c in calls if c.name in {t.name for t in item.expected_tools}]
        if matched and item.input:
            prompt = load_prompt("tool_args_semantic")
            grades: list[float] = []
            rationales: list[str] = []
            for call in matched:
                grade, _ = await judge.judge(
                    prompt,
                    {
                        "input": item.input,
                        "tool_name": call.name,
                        "tool_args": json.dumps(call.args, ensure_ascii=False),
                    },
                    RubricScore,
                )
                grades.append(rubric_to_unit(grade.score))
                rationales.append(f"{call.name}: {grade.rationale}")
            sub["args_semantic"] = sum(grades) / len(grades)
            details["args_rationales"] = rationales
            versions.append(f"{prompt.name}@{prompt.version}")

        # result used in the final answer
        last_with_result = next((c for c in reversed(calls) if c.result is not None), None)
        if last_with_result is not None and item.output:
            prompt = load_prompt("result_used")
            used, _ = await judge.judge(
                prompt,
                {
                    "tool_name": last_with_result.name,
                    "tool_result": json.dumps(
                        last_with_result.result, ensure_ascii=False, default=str
                    )[:4000],
                    "output": item.output,
                },
                YesNo,
            )
            sub["result_used"] = 1.0 if used.answer == "yes" else 0.0
            details["result_used_rationale"] = used.rationale
            versions.append(f"{prompt.name}@{prompt.version}")

        value = sum(sub.values()) / len(sub)
        parts = ", ".join(f"{k} {v:.2f}" for k, v in sub.items())
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=f"{parts}; missing tools: {details['missing'] or 'none'}",
            sub_scores=sub,
            details=details,
            judge_prompt_version=";".join(versions) or None,
        )
