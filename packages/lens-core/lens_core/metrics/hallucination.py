"""Hallucination (SPEC.md §5.2). Lower is better.

    hallucination = (|contradicted| + 0.5 · |unverifiable|) / |claims|

Claims are extracted as for faithfulness, then verified against the contexts
(``claim_verification``); when the item has no contexts the judge falls back to
conservative world knowledge (``hallucination_world``). Contradicted claims
count fully, unverifiable claims half, so the metric distinguishes fabrication
from merely ungrounded statements (both are reported as sub-scores).
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.faithfulness import extract_claims, verify_claims
from lens_core.metrics.registry import register_metric

UNVERIFIABLE_WEIGHT = 0.5


@register_metric
class Hallucination(BaseMetric):
    name: ClassVar[str] = "hallucination"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"output"})
    higher_is_better: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Weighted share of output claims contradicted (1.0) or unverifiable (0.5) "
        "against context or world knowledge."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        claims, v_extract = await extract_claims(item, judge)
        if not claims:
            return MetricResult(
                metric=self.name,
                version=self.version,
                value=0.0,
                rationale="Output contains no factual claims.",
                judge_prompt_version=v_extract,
            )
        world = len(item.contexts) == 0
        verdicts, v_verify = await verify_claims(claims, item, judge, world_knowledge=world)
        n = len(claims)
        contradicted = sum(1 for v in verdicts if v.verdict == "contradicted")
        unverifiable = sum(1 for v in verdicts if v.verdict == "unverifiable")
        value = (contradicted + UNVERIFIABLE_WEIGHT * unverifiable) / n
        flagged = [v.model_dump() for v in verdicts if v.verdict != "supported"]
        basis = "world knowledge (no contexts)" if world else "retrieved contexts"
        rationale = (
            f"{contradicted} contradicted, {unverifiable} unverifiable of {n} claims vs {basis}"
        )
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=rationale,
            sub_scores={
                "contradicted_rate": contradicted / n,
                "unverifiable_rate": unverifiable / n,
                "n_claims": float(n),
            },
            details={
                "claims": [v.model_dump() for v in verdicts],
                "flagged": flagged,
                "basis": basis,
            },
            judge_prompt_version=f"{v_extract};{v_verify}",
        )
