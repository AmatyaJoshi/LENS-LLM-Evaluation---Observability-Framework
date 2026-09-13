"""Inter-rater agreement (SPEC.md §5.3): Cohen's κ, Krippendorff's α, Spearman ρ.

Pure Python, no SciPy. Formulas are documented inline so the numbers in the
Judge Quality page are auditable.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    """ρ = Pearson correlation of the rank vectors. Returns 0.0 when undefined."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (vx * vy) if vx and vy else 0.0


def cohen_kappa(a: Sequence[object], b: Sequence[object]) -> float:
    """κ = (p_o − p_e) / (1 − p_e) for nominal labels; 1.0 when both raters agree
    perfectly and p_e = 1 (degenerate single-label case)."""
    if len(a) != len(b) or not a:
        return 0.0
    n = len(a)
    p_o = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    p_e = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if p_e >= 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


def binarize(values: Sequence[float], threshold: float = 0.5) -> list[int]:
    return [1 if v >= threshold else 0 for v in values]


def krippendorff_alpha(ratings: Sequence[Sequence[float | None]], level: str = "interval") -> float:
    """α = 1 − D_o / D_e over a raters × items matrix (``None`` = missing).

    Distance metric: ``nominal`` (0/1), ``ordinal`` (squared rank-based), or
    ``interval`` (squared difference). Items with fewer than two ratings are ignored.
    """
    if not ratings:
        return 0.0
    n_items = max(len(r) for r in ratings)
    columns: list[list[float]] = []
    for j in range(n_items):
        col: list[float] = [float(r[j]) for r in ratings if j < len(r) and r[j] is not None]  # type: ignore[arg-type]
        if len(col) >= 2:
            columns.append(col)
    if not columns:
        return 0.0
    all_values = [v for col in columns for v in col]
    if level == "ordinal":
        distinct = sorted(set(all_values))
        rank_of = {v: i for i, v in enumerate(distinct)}
        counts = Counter(all_values)

        def dist(a: float, b: float) -> float:
            if a == b:
                return 0.0
            lo, hi = sorted((rank_of[a], rank_of[b]))
            between = sum(counts[distinct[k]] for k in range(lo, hi + 1))
            return (between - (counts[a] + counts[b]) / 2) ** 2

    elif level == "nominal":

        def dist(a: float, b: float) -> float:
            return 0.0 if a == b else 1.0

    else:

        def dist(a: float, b: float) -> float:
            return (a - b) ** 2

    d_o_num = 0.0
    d_o_den = 0
    for col in columns:
        m = len(col)
        d_o_num += sum(dist(col[i], col[k]) for i in range(m) for k in range(m) if i != k) / (m - 1)
        d_o_den += m
    d_o = d_o_num / d_o_den if d_o_den else 0.0
    n = len(all_values)
    d_e = sum(
        dist(a, b) for i, a in enumerate(all_values) for k, b in enumerate(all_values) if i != k
    ) / (n * (n - 1))
    if d_e == 0:
        return 1.0 if d_o == 0 else 0.0
    return 1 - d_o / d_e


class AgreementReport(BaseModel):
    metric: str
    judge: str
    reference: str  # "human" or another judge
    n: int
    cohen_kappa: float
    krippendorff_alpha: float
    spearman_rho: float
    mean_abs_error: float
    threshold: float = 0.5


def agreement(
    metric: str,
    judge: str,
    judge_scores: Sequence[float],
    reference: str,
    reference_scores: Sequence[float],
    *,
    threshold: float = 0.5,
) -> AgreementReport:
    n = min(len(judge_scores), len(reference_scores))
    js: list[float] = [float(v) for v in judge_scores[:n]]
    rs: list[float] = [float(v) for v in reference_scores[:n]]
    return AgreementReport(
        metric=metric,
        judge=judge,
        reference=reference,
        n=n,
        cohen_kappa=cohen_kappa(binarize(js, threshold), binarize(rs, threshold)) if n else 0.0,
        krippendorff_alpha=(
            krippendorff_alpha([list(js), list(rs)], level="interval") if n else 0.0
        ),
        spearman_rho=spearman_rho(js, rs) if n else 0.0,
        mean_abs_error=sum(abs(a - b) for a, b in zip(js, rs, strict=True)) / n if n else 0.0,
        threshold=threshold,
    )
