"""Shared helpers for the training pipelines (SPEC.md §7.3): seeding, results IO, metrics."""

from __future__ import annotations

import json
import os
import random
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"


def set_seed(seed: int = 13) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return os.environ.get("GITHUB_SHA", "nogit")[:12] or "nogit"


def write_results(name: str, payload: dict[str, Any]) -> Path:
    """Write a results file the README can cite (CLAUDE.md: numbers must point to a file)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = RESULTS_DIR / f"{stamp}_{git_sha()}_{name}.json"
    payload = {"generated_at": datetime.now(UTC).isoformat(), "git_sha": git_sha(), **payload}
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_default), encoding="utf-8"
    )
    print(f"wrote results -> {path}")
    return path


def _default(o: Any) -> Any:
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    return str(o)


def binary_metrics(
    y_true: list[int], y_pred: list[int], y_score: list[float] | None = None
) -> dict[str, float]:
    """Precision, recall, F1, accuracy and (optional) AUROC without sklearn as a hard dep."""
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    acc = (tp + tn) / len(y_true) if y_true else 0.0
    out = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": acc,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }
    if y_score is not None:
        out["auroc"] = auroc(y_true, y_score)
        out["fpr"] = fp / (fp + tn) if (fp + tn) else 0.0
    return out


def auroc(y_true: list[int], y_score: list[float]) -> float:
    """AUROC via the Mann-Whitney U statistic (rank-sum)."""
    pos = [s for t, s in zip(y_true, y_score, strict=True) if t == 1]
    neg = [s for t, s in zip(y_true, y_score, strict=True) if t == 0]
    if not pos or not neg:
        return 0.0
    order = sorted(range(len(y_score)), key=lambda i: y_score[i])
    ranks = [0.0] * len(y_score)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and y_score[order[j + 1]] == y_score[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum_pos = sum(ranks[i] for i, t in enumerate(y_true) if t == 1)
    u = rank_sum_pos - len(pos) * (len(pos) + 1) / 2
    return u / (len(pos) * len(neg))
