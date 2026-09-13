"""Context precision (SPEC.md §5.2).

    precision@k  = |useful passages among the first k| / k
    value        = Σ_k precision@k · rel_k  /  Σ_k rel_k      (rel_k ∈ {0,1})

Each retrieved passage is judged useful / not useful for answering the input
(and the reference answer when present) via ``context_usefulness``. The rank
weighting rewards retrievers that put useful passages first. No useful passage
gives 0.
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import YesNo, YesNoList, numbered
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric


def rank_weighted_precision(relevant: list[bool]) -> float:
    if not any(relevant):
        return 0.0
    total = 0.0
    hits = 0
    for k, rel in enumerate(relevant, start=1):
        if rel:
            hits += 1
            total += hits / k
    return total / sum(relevant)


@register_metric
class ContextPrecision(BaseMetric):
    name: ClassVar[str] = "context_precision"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"input", "contexts"})
    description: ClassVar[str] = (
        "Rank-weighted fraction of retrieved passages judged useful for answering."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        prompt = load_prompt("context_usefulness")
        parsed, _ = await judge.judge(
            prompt,
            {
                "input": item.input or "",
                "expected_output": item.expected_output or "",
                "contexts": numbered(item.contexts),
            },
            YesNoList,
            max_tokens=2048,
        )
        answers: list[YesNo] = list(parsed.answers)[: len(item.contexts)]
        while len(answers) < len(item.contexts):
            answers.append(YesNo(answer="no", rationale="missing verdict"))
        relevant = [a.answer == "yes" for a in answers]
        value = rank_weighted_precision(relevant)
        useful = sum(relevant)
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=(
                f"{useful}/{len(relevant)} passages useful; rank-weighted precision {value:.2f}"
            ),
            sub_scores={
                "useful_fraction": useful / len(relevant) if relevant else 0.0,
                "n_contexts": float(len(relevant)),
            },
            details={"per_context": [a.model_dump() for a in answers]},
            judge_prompt_version=f"{prompt.name}@{prompt.version}",
        )
