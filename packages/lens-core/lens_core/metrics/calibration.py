"""Calibration (SPEC.md §5.2, Sentinel-specific). No judge calls.

    value = 1 − Brier,   Brier = mean (confidence − outcome)²

Predictions come from ``item.metadata["predictions"]`` as a list of
``{"confidence": float, "outcome": 0|1}`` (Sentinel emits its ``Finding.confidence``
and the verification outcome as ``sentinel.predictions`` on the root span, which
the trajectory copies into metadata). Details carry the reliability diagram
bins and ECE for the dashboard.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.calibration import brier_score, expected_calibration_error, reliability_bins
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric

PREDICTION_KEYS = ("predictions", "sentinel.predictions")


def extract_predictions(item: EvalItem) -> list[tuple[float, float]]:
    raw: Any = None
    for key in PREDICTION_KEYS:
        if key in item.metadata:
            raw = item.metadata[key]
            break
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[tuple[float, float]] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        conf = p.get("confidence")
        outcome = p.get("outcome", p.get("verified"))
        if isinstance(conf, int | float) and outcome is not None:
            out.append((max(0.0, min(1.0, float(conf))), 1.0 if bool(outcome) else 0.0))
    return out


@register_metric
class Calibration(BaseMetric):
    name: ClassVar[str] = "calibration"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset()
    description: ClassVar[str] = (
        "1 − Brier score of the agent's stated confidence against verified outcomes."
    )

    def missing(self, item: EvalItem) -> list[str]:
        return [] if extract_predictions(item) else ["metadata.predictions"]

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        preds = extract_predictions(item)
        confidences = [c for c, _ in preds]
        outcomes = [o for _, o in preds]
        brier = brier_score(confidences, outcomes)
        ece = expected_calibration_error(confidences, outcomes)
        bins = reliability_bins(confidences, outcomes)
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=1 - brier,
            rationale=f"Brier {brier:.3f}, ECE {ece:.3f} over {len(preds)} predictions",
            sub_scores={"brier": brier, "ece": ece, "n_predictions": float(len(preds))},
            details={"bins": [b.model_dump() for b in bins]},
        )
