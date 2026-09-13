"""Context recall (SPEC.md §5.2).

    recall = |sentences of the expected answer attributable to the contexts| / |sentences|

The reference answer is split into sentences; the judge labels each as
attributable or not to the numbered passages (``attribution`` prompt). Measures
whether retrieval brought back everything needed to write the ideal answer.
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import YesNo, YesNoList, numbered, split_sentences
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric


@register_metric
class ContextRecall(BaseMetric):
    name: ClassVar[str] = "context_recall"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"expected_output", "contexts"})
    description: ClassVar[str] = (
        "Share of reference-answer sentences that the retrieved passages can support."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        assert item.expected_output is not None
        sentences = split_sentences(item.expected_output) or [item.expected_output.strip()]
        prompt = load_prompt("attribution")
        parsed, _ = await judge.judge(
            prompt,
            {"contexts": numbered(item.contexts), "sentences": numbered(sentences)},
            YesNoList,
            max_tokens=2048,
        )
        answers: list[YesNo] = list(parsed.answers)[: len(sentences)]
        while len(answers) < len(sentences):
            answers.append(YesNo(answer="no", rationale="missing verdict"))
        attributed = sum(1 for a in answers if a.answer == "yes")
        n = len(sentences)
        missing = [s for s, a in zip(sentences, answers, strict=True) if a.answer == "no"]
        rationale = f"{attributed}/{n} reference sentences supported by retrieved context"
        if missing:
            rationale += f"; missing e.g. “{missing[0][:80]}”"
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=attributed / n,
            rationale=rationale,
            sub_scores={"n_sentences": float(n)},
            details={
                "sentences": sentences,
                "per_sentence": [a.model_dump() for a in answers],
                "missing": missing,
            },
            judge_prompt_version=f"{prompt.name}@{prompt.version}",
        )
