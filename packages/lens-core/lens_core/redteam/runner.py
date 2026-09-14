"""Red-team runner (SPEC.md §6.4): expand probes with mutators, attack the target
concurrently, score each attempt, and aggregate attack success rate.

ASR is reported overall, per category and per mutator; ``detector_caught`` is the
number of *successful* attacks the live detector also flagged (SPEC.md §6.4).
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from lens_core.judges.base import Judge
from lens_core.redteam.mutators import DETERMINISTIC, LLM_MUTATORS, apply_deterministic, apply_llm
from lens_core.redteam.probes import Probe
from lens_core.redteam.scoring import ProbeScore, score_probe
from lens_core.redteam.targets import Target


class ProbeOutcome(BaseModel):
    probe_id: str
    parent_probe_id: str | None
    category: str
    tactic: str
    mutator: str | None
    messages: list[dict[str, Any]]
    response: str
    success: bool
    success_reason: str
    method: str
    detector_score: float
    detector_flagged: bool
    judge_rationale: str | None = None
    trace_id: str | None = None
    latency_ms: float = 0.0


class RunReport(BaseModel):
    total: int = 0
    successes: int = 0
    asr: float = 0.0
    detector_caught: int = 0
    detector_caught_rate: float = 0.0
    by_category: dict[str, dict[str, float]] = Field(default_factory=dict)
    by_mutator: dict[str, dict[str, float]] = Field(default_factory=dict)
    outcomes: list[ProbeOutcome] = Field(default_factory=list)


class RedteamRunner:
    def __init__(
        self,
        target: Target,
        *,
        judge: Judge | None = None,
        mutators: list[str] | None = None,
        concurrency: int = 4,
    ) -> None:
        self.target = target
        self.judge = judge
        self.mutators = mutators or []
        self._sem = asyncio.Semaphore(concurrency)

    def expand(self, probes: list[Probe]) -> list[Probe]:
        """Seed probes plus deterministic mutator variants (lineage preserved)."""
        deterministic = [m for m in self.mutators if m in DETERMINISTIC]
        expanded: list[Probe] = []
        for probe in probes:
            expanded.append(probe)
            expanded.extend(apply_deterministic(probe, deterministic))
        return expanded

    async def _run_one(self, probe: Probe) -> ProbeOutcome:
        import time

        messages = probe.to_messages()
        async with self._sem:
            t0 = time.perf_counter()
            response = await self.target.send(probe, messages)
            latency = (time.perf_counter() - t0) * 1000
            score: ProbeScore = await score_probe(probe, response, self.judge)
        return ProbeOutcome(
            probe_id=probe.id,
            parent_probe_id=probe.parent_probe_id,
            category=probe.category,
            tactic=probe.tactic,
            mutator=probe.mutator,
            messages=[m.model_dump() for m in messages],
            response=response.output,
            success=score.success,
            success_reason=score.reason,
            method=score.method,
            detector_score=score.detector_score,
            detector_flagged=score.detector_flagged,
            judge_rationale=score.judge_rationale,
            trace_id=response.trace_id,
            latency_ms=latency,
        )

    async def run(self, probes: list[Probe]) -> RunReport:
        expanded = self.expand(probes)
        llm_names = [m for m in self.mutators if m in LLM_MUTATORS]
        if llm_names and self.judge is not None:
            variants = await asyncio.gather(*(apply_llm(p, llm_names, self.judge) for p in probes))
            for group in variants:
                expanded.extend(group)
        outcomes = list(await asyncio.gather(*(self._run_one(p) for p in expanded)))
        return aggregate(outcomes)


def _bucket(outcomes: list[ProbeOutcome], key: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[ProbeOutcome]] = {}
    for o in outcomes:
        k = getattr(o, key) or "seed"
        groups.setdefault(k, []).append(o)
    out: dict[str, dict[str, float]] = {}
    for k, items in groups.items():
        succ = sum(1 for o in items if o.success)
        out[k] = {
            "total": len(items),
            "successes": succ,
            "asr": succ / len(items) if items else 0.0,
        }
    return out


def aggregate(outcomes: list[ProbeOutcome]) -> RunReport:
    total = len(outcomes)
    successes = sum(1 for o in outcomes if o.success)
    caught = sum(1 for o in outcomes if o.success and o.detector_flagged)
    return RunReport(
        total=total,
        successes=successes,
        asr=successes / total if total else 0.0,
        detector_caught=caught,
        detector_caught_rate=caught / successes if successes else 0.0,
        by_category=_bucket(outcomes, "category"),
        by_mutator=_bucket(outcomes, "mutator"),
        outcomes=outcomes,
    )
