"""Judge calibration (SPEC.md §5.3): reliability bins, Brier score, ECE,
temperature scaling and isotonic regression fitted on the human gold set.

Stored per (judge, metric) and applied to raw judge scores before they are
compared to humans or used for CI gating.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, Field


class ReliabilityBin(BaseModel):
    lo: float
    hi: float
    n: int
    mean_predicted: float
    mean_observed: float


def brier_score(predicted: Sequence[float], observed: Sequence[float]) -> float:
    """Mean squared error between predicted probability and observed outcome (0/1 or [0,1])."""
    if not predicted:
        return 0.0
    return sum((p - o) ** 2 for p, o in zip(predicted, observed, strict=True)) / len(predicted)


def reliability_bins(
    predicted: Sequence[float], observed: Sequence[float], n_bins: int = 10
) -> list[ReliabilityBin]:
    bins: list[ReliabilityBin] = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [
            i for i, p in enumerate(predicted) if (lo <= p < hi) or (b == n_bins - 1 and p == 1.0)
        ]
        if not idx:
            bins.append(ReliabilityBin(lo=lo, hi=hi, n=0, mean_predicted=0.0, mean_observed=0.0))
            continue
        bins.append(
            ReliabilityBin(
                lo=lo,
                hi=hi,
                n=len(idx),
                mean_predicted=sum(predicted[i] for i in idx) / len(idx),
                mean_observed=sum(observed[i] for i in idx) / len(idx),
            )
        )
    return bins


def expected_calibration_error(
    predicted: Sequence[float], observed: Sequence[float], n_bins: int = 10
) -> float:
    """ECE = Σ_b (n_b / N) · |mean_pred_b − mean_obs_b|."""
    n = len(predicted)
    if n == 0:
        return 0.0
    return sum(
        b.n / n * abs(b.mean_predicted - b.mean_observed)
        for b in reliability_bins(predicted, observed, n_bins)
    )


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(1 - eps, max(eps, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class TemperatureScaler(BaseModel):
    """p' = σ(logit(p) / T). T fitted by grid search on negative log-likelihood."""

    temperature: float = 1.0

    @classmethod
    def fit(cls, predicted: Sequence[float], observed: Sequence[float]) -> TemperatureScaler:
        if not predicted:
            return cls()
        best_t, best_nll = 1.0, float("inf")
        for i in range(1, 400):
            t = i / 40  # 0.025 .. 10
            nll = 0.0
            for p, o in zip(predicted, observed, strict=True):
                q = min(1 - 1e-6, max(1e-6, _sigmoid(_logit(p) / t)))
                nll -= o * math.log(q) + (1 - o) * math.log(1 - q)
            if nll < best_nll:
                best_t, best_nll = t, nll
        return cls(temperature=best_t)

    def apply(self, p: float) -> float:
        return _sigmoid(_logit(p) / self.temperature)


class IsotonicCalibrator(BaseModel):
    """Monotone step function fitted with pool-adjacent-violators (PAV)."""

    xs: list[float] = Field(default_factory=list)
    ys: list[float] = Field(default_factory=list)

    @classmethod
    def fit(cls, predicted: Sequence[float], observed: Sequence[float]) -> IsotonicCalibrator:
        if not predicted:
            return cls()
        pairs = sorted(zip(predicted, observed, strict=True))
        # blocks: [sum_y, count, x_min, x_max]
        blocks: list[list[float]] = [[y, 1, x, x] for x, y in pairs]
        i = 0
        while i < len(blocks) - 1:
            a, b = blocks[i], blocks[i + 1]
            if a[0] / a[1] > b[0] / b[1]:
                blocks[i : i + 2] = [[a[0] + b[0], a[1] + b[1], a[2], b[3]]]
                i = max(i - 1, 0)
            else:
                i += 1
        # xs = upper edge of each monotone block, ys = block mean (a right-continuous step function,
        # which is the PAV solution and therefore never worse than identity on the fit set).
        xs = [b[3] for b in blocks]
        ys = [b[0] / b[1] for b in blocks]
        return cls(xs=xs, ys=ys)

    def apply(self, p: float) -> float:
        if not self.xs:
            return p
        for x_max, y in zip(self.xs, self.ys, strict=True):
            if p <= x_max:
                return y
        return self.ys[-1]


class CalibrationReport(BaseModel):
    judge: str
    metric: str
    n: int
    brier_raw: float
    brier_temperature: float
    brier_isotonic: float
    ece_raw: float
    ece_temperature: float
    ece_isotonic: float
    temperature: float
    bins_raw: list[ReliabilityBin]
    bins_isotonic: list[ReliabilityBin]


def calibrate(
    judge: str, metric: str, predicted: Sequence[float], observed: Sequence[float]
) -> CalibrationReport:
    ts = TemperatureScaler.fit(predicted, observed)
    iso = IsotonicCalibrator.fit(predicted, observed)
    p_t = [ts.apply(p) for p in predicted]
    p_i = [iso.apply(p) for p in predicted]
    return CalibrationReport(
        judge=judge,
        metric=metric,
        n=len(predicted),
        brier_raw=brier_score(predicted, observed),
        brier_temperature=brier_score(p_t, observed),
        brier_isotonic=brier_score(p_i, observed),
        ece_raw=expected_calibration_error(predicted, observed),
        ece_temperature=expected_calibration_error(p_t, observed),
        ece_isotonic=expected_calibration_error(p_i, observed),
        temperature=ts.temperature,
        bins_raw=reliability_bins(predicted, observed),
        bins_isotonic=reliability_bins(p_i, observed),
    )
