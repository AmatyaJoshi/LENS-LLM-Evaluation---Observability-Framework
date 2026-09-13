"""Faithfulness (SPEC.md §5.2).

    faithfulness = |claims supported by the contexts| / |claims|

1. Claim extraction: the judge decomposes the output into atomic factual claims
   (``claim_extraction`` prompt).
2. Claim verification: each claim is labelled supported / contradicted /
   unverifiable against the numbered contexts (``claim_verification`` prompt,
   NLI-style; a local DeBERTa NLI judge can be substituted via the router's
   ``nli`` tier).
3. Value is the supported fraction; unsupported claims are reported in details.

An output with no factual claims (greetings, refusals) is vacuously faithful (1.0).
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import Claims, ClaimVerdict, Verdicts, numbered
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric


async def extract_claims(item: EvalItem, judge: Judge) -> tuple[list[str], str]:
    prompt = load_prompt("claim_extraction")
    parsed, _ = await judge.judge(
        prompt, {"input": item.input or "", "output": item.output or ""}, Claims
    )
    claims = [c.strip() for c in parsed.claims if c and c.strip()]
    return claims, f"{prompt.name}@{prompt.version}"


async def verify_claims(
    claims: list[str], item: EvalItem, judge: Judge, *, world_knowledge: bool = False
) -> tuple[list[ClaimVerdict], str]:
    """Label each claim against the contexts (or world knowledge when there are none)."""
    if world_knowledge:
        prompt = load_prompt("hallucination_world")
        variables = {"input": item.input or "", "claims": numbered(claims)}
    else:
        prompt = load_prompt("claim_verification")
        variables = {"contexts": numbered(item.contexts), "claims": numbered(claims)}
    parsed, _ = await judge.judge(prompt, variables, Verdicts, max_tokens=2048)
    verdicts = list(parsed.verdicts)
    # Align defensively: pad missing verdicts as unverifiable, drop extras.
    while len(verdicts) < len(claims):
        verdicts.append(ClaimVerdict(claim=claims[len(verdicts)], verdict="unverifiable"))
    return verdicts[: len(claims)], f"{prompt.name}@{prompt.version}"


@register_metric
class Faithfulness(BaseMetric):
    name: ClassVar[str] = "faithfulness"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"output", "contexts"})
    description: ClassVar[str] = (
        "Fraction of atomic claims in the output supported by the retrieved contexts."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        claims, v_extract = await extract_claims(item, judge)
        if not claims:
            return MetricResult(
                metric=self.name,
                version=self.version,
                value=1.0,
                rationale="Output contains no factual claims; vacuously faithful.",
                details={"claims": []},
                judge_prompt_version=v_extract,
            )
        verdicts, v_verify = await verify_claims(claims, item, judge)
        n = len(claims)
        supported = sum(1 for v in verdicts if v.verdict == "supported")
        contradicted = sum(1 for v in verdicts if v.verdict == "contradicted")
        unverifiable = n - supported - contradicted
        unsupported = [v.model_dump() for v in verdicts if v.verdict != "supported"]
        rationale = f"{supported}/{n} claims supported by context"
        if unsupported:
            worst = unsupported[0]
            rationale += f"; e.g. {worst['verdict']}: “{worst['claim']}”"
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=supported / n,
            rationale=rationale,
            sub_scores={
                "supported_rate": supported / n,
                "contradicted_rate": contradicted / n,
                "unverifiable_rate": unverifiable / n,
                "n_claims": float(n),
            },
            details={"claims": [v.model_dump() for v in verdicts], "unsupported": unsupported},
            judge_prompt_version=f"{v_extract};{v_verify}",
        )
