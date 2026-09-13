"""Task completion (SPEC.md §5.2).

    rubric   = (grade − 1) / 4                           grade ∈ 1..5 (``task_completion``)
    pairwise = mean over both orders of win=1 / tie=0.5 / loss=0 vs the reference answer
    value    = mean(rubric, pairwise) when a reference exists, else rubric

Position bias control: the pairwise comparison is run twice with A/B swapped
and averaged (SPEC.md §5.3). Verbosity bias is addressed in the prompt rubric
("do not prefer an answer for being longer").
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import PairwiseChoice, RubricScore, rubric_to_unit
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric


async def pairwise_vs_reference(item: EvalItem, judge: Judge) -> tuple[float, list[str]]:
    """Return (score in [0,1], rationales) with order swapped and averaged."""
    prompt = load_prompt("pairwise")
    assert item.output is not None and item.expected_output is not None
    first, _ = await judge.judge(
        prompt,
        {"input": item.input or "", "a": item.output, "b": item.expected_output},
        PairwiseChoice,
    )
    second, _ = await judge.judge(
        prompt,
        {"input": item.input or "", "a": item.expected_output, "b": item.output},
        PairwiseChoice,
    )
    s1 = {"A": 1.0, "tie": 0.5, "B": 0.0}[first.winner]
    s2 = {"B": 1.0, "tie": 0.5, "A": 0.0}[second.winner]
    return (s1 + s2) / 2, [first.rationale, second.rationale]


@register_metric
class TaskCompletion(BaseMetric):
    name: ClassVar[str] = "task_completion"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"input", "output"})
    description: ClassVar[str] = (
        "Rubric grade of task accomplishment, blended with position-swapped pairwise vs reference."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        prompt = load_prompt("task_completion")
        rubric, _ = await judge.judge(
            prompt,
            {
                "input": item.input or "",
                "expected_output": item.expected_output or "",
                "output": item.output or "",
            },
            RubricScore,
        )
        rubric_unit = rubric_to_unit(rubric.score)
        sub = {"rubric": rubric_unit}
        details: dict[str, object] = {"evidence_spans": rubric.evidence_spans}
        versions = [f"{prompt.name}@{prompt.version}"]
        value = rubric_unit
        rationale = f"rubric {rubric.score}/5: {rubric.rationale}"
        if item.expected_output:
            pw, rats = await pairwise_vs_reference(item, judge)
            sub["pairwise_vs_reference"] = pw
            details["pairwise_rationales"] = rats
            versions.append(f"pairwise@{load_prompt('pairwise').version}")
            value = (rubric_unit + pw) / 2
            rationale += f"; pairwise vs reference {pw:.2f} (order-swapped)"
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=rationale,
            sub_scores=sub,
            details=details,
            judge_prompt_version=";".join(versions),
        )
