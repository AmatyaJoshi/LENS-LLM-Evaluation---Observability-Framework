"""Custom metrics (SPEC.md §5.1): YAML rubric metrics and Python plug-ins.

YAML rubric format::

    name: tone_professional
    version: 1
    description: Is the reply professional and free of slang?
    requires: [input, output]          # any of input, output, contexts, expected_output
    scale: 5                           # 1..scale, mapped to [0,1]
    criteria:
      - Uses complete sentences and no slang
      - Stays courteous even when refusing
    examples:                          # optional few-shots
      - output: "Yo, can't help with that lol"
        score: 1
      - output: "I'm sorry, I can't help with that request."
        score: 5

Python plug-ins are files defining ``@register_metric`` classes; see
``registry.load_metric_module``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, ConfigDict, Field

from lens_core.judges.base import Judge
from lens_core.judges.prompts import Prompt
from lens_core.metrics._shared import numbered
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric

DEFAULT_REQUIRES: tuple[Requirement, ...] = ("input", "output")


class RubricGrade(BaseModel):
    score: int
    rationale: str = ""
    evidence_spans: list[str] = Field(default_factory=list)


class RubricSpec(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    name: str
    version: str = "1"
    description: str = ""
    requires: list[Requirement] = Field(default_factory=lambda: list(DEFAULT_REQUIRES))
    scale: int = Field(default=5, ge=2, le=10)
    criteria: list[str]
    examples: list[dict[str, Any]] = Field(default_factory=list)
    higher_is_better: bool = True


def build_rubric_prompt(spec: RubricSpec) -> Prompt:
    examples = "\n".join(
        f'Example output: "{e.get("output", "")}" -> '
        f'{{"score": {e.get("score")}, "rationale": "{e.get("rationale", "")}"}}'
        for e in spec.examples
    )
    system = (
        f"You grade an assistant output on the metric '{spec.name}': {spec.description}\n"
        f"Criteria:\n{numbered(spec.criteria)}\n"
        f"Give an integer score from 1 (fails all criteria) to {spec.scale} (meets all criteria). "
        'Reply with JSON only: {"score": <int>, "rationale": "...", "evidence_spans": ["..."]}.'
        + (f"\n\n{examples}" if examples else "")
    )
    user = (
        "User input:\n{{input}}\n\nExpected output (may be empty):\n{{expected_output}}\n\n"
        "Contexts (may be empty):\n{{contexts}}\n\nAssistant output:\n{{output}}\n\nReturn JSON."
    )
    return Prompt(
        name=f"rubric_{spec.name}", version=spec.version, output="json", system=system, user=user
    )


def make_rubric_metric(spec: RubricSpec) -> type[BaseMetric]:
    prompt = build_rubric_prompt(spec)

    class _RubricMetric(BaseMetric):
        name: ClassVar[str] = spec.name
        version: ClassVar[str] = spec.version
        requires: ClassVar[frozenset[Requirement]] = frozenset(spec.requires)
        higher_is_better: ClassVar[bool] = spec.higher_is_better
        description: ClassVar[str] = spec.description

        async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
            grade, _ = await judge.judge(
                prompt,
                {
                    "input": item.input or "",
                    "expected_output": item.expected_output or "",
                    "contexts": numbered(item.contexts),
                    "output": item.output or "",
                },
                RubricGrade,
            )
            score = max(1, min(spec.scale, grade.score))
            return MetricResult(
                metric=self.name,
                version=self.version,
                value=(score - 1) / (spec.scale - 1),
                rationale=f"{score}/{spec.scale}: {grade.rationale}",
                details={"evidence_spans": grade.evidence_spans, "criteria": spec.criteria},
                judge_prompt_version=f"{prompt.name}@{prompt.version}",
            )

    _RubricMetric.__name__ = f"Rubric_{spec.name}"
    return _RubricMetric


def load_rubric(path: Path) -> type[BaseMetric]:
    spec = RubricSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    cls = make_rubric_metric(spec)
    register_metric(cls)
    return cls
